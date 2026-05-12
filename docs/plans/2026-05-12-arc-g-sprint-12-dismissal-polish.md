# Arc G — Sprint 12: Dismissal lifecycle + web Undo + briefing surface + tier_gap JSON

**Status:** Drafted 2026-05-12 after Sprint 11 shipped (main `6aaf725`). Sprint 12 / Arc G closes the dismissal-lifecycle gaps and exposes `tier_gap` data to external tooling.

## Context

Sprint 11 landed the dismiss-suggestion workflow but left rough edges:
- Dismissals are permanent until `--undo-dismiss` is run — no auto-expiry, so the operator must remember to revisit them.
- The web UI has Accept + Dismiss buttons on the suggestions page but no way to LIST dismissed entries or UNDO from the browser.
- The briefing (`--briefing`) doesn't surface dismissed repos, so an operator generating their weekly digest has no visibility into what's currently suppressed.
- `tier_gap` data flows through web template and Excel sheet but has no CLI/JSON export surface for external tooling.

Sprint 12 closes all four loops.

## Inventory

| # | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| 12.1 | Auto-expire dismissals after N days + persistent audit trail | medium | none | ⏳ |
| 12.2 | Web `/initiatives/dismissed` page + per-row Undo button + nav link | medium | none | ⏳ |
| 12.3 | Briefing "Currently Dismissed" section | small-medium | none | ⏳ |
| 12.4 | `audit report --tier-gaps [--format json]` — dump per-repo tier gaps + sources for external tooling | medium | none | ⏳ |
| 12.5 | Sprint 12 closeout + PR | small | 12.1-12.4 | ⏳ |

**Test count target:** 1890 → ~1950 (+50-70 new tests).

## Subagent dispatch plan

Two waves to avoid `src/cli.py` conflicts:

### Wave 1 — three parallel Sonnet subagents

- **Agent A — Item 12.2** (web Undo + list page). Touches `src/serve/routes.py`, `src/serve/templates/*.html`, `tests/test_initiatives_suggestions_route.py`.
- **Agent B — Item 12.3** (briefing dismissals section). Touches `src/briefing.py`, `tests/test_briefing.py`.
- **Agent C — Item 12.4** (`audit report --tier-gaps`). Touches `src/cli.py` (report subparser only), maybe new `src/tier_gaps_export.py`, `tests/`.

Agent A + B + C have no file overlap.

### Wave 2 — single Sonnet subagent

- **Agent D — Item 12.1** (auto-expire + audit trail). Touches `src/suggest_initiatives.py` + `src/cli.py` (triage subparser). After Agent C lands, Agent D's `cli.py` patch will be against a slightly newer base. Cherry-pick will rebase cleanly because the two patches edit different subparsers (`report` vs `triage`).

### Closeout (lead)

- Item 12.5 — closeout doc + PR + merge. Apply `/verify` skill (visual UI check on dismissed page) and `/code-review` skill (mandatory for ~600+ LoC diff).

**Skills usage:**
- `verify` skill (Playwright MCP) after Wave 1 lands — screenshot `/initiatives/dismissed` page and `/initiatives/suggestions` (now with Undo button on dismissed cards if any persist).
- `code-review` skill (multi-agent gate) before merging the Sprint 12 PR — diff exceeds 200 LoC threshold from demand-elegance rule.

**Subagent brief preamble:** mandatory cwd discipline preamble in every brief (Sprint 8 / 10 / 11 retro lessons). Each brief also includes the "always `git add` closeout docs immediately" note from Sprint 11 retro.

## Schema + code references

### 12.1 — Auto-expire + audit trail

**Schema additions to `DismissedSuggestion`** in `src/suggest_initiatives.py`:

```python
@dataclass(frozen=True)
class DismissedSuggestion:
    repo_name: str
    reason: str
    dismissed_at: str
    dismissed_by: str
    expires_at: str | None = None  # NEW — ISO date or None for permanent

@dataclass(frozen=True)
class DismissalEvent:
    """Audit-trail entry for a dismiss/undo/expire action."""
    repo_name: str
    event_type: str  # "dismissed" | "undone" | "expired"
    occurred_at: str  # ISO timestamp
    actor: str       # operator_identity() or "system" (for auto-expire)
    reason: str = "" # optional context
```

Persistence schema (versioned, additive):

```json
{
  "version": 2,
  "items": [
    {"repo_name": "...", "reason": "...", "dismissed_at": "...", "dismissed_by": "...", "expires_at": null}
  ],
  "events": [
    {"repo_name": "...", "event_type": "dismissed", "occurred_at": "...", "actor": "...", "reason": "..."}
  ]
}
```

Sprint 11's v1 schema (no `expires_at`, no `events` array) MUST still load cleanly — pre-Sprint-12 entries default to `expires_at=None` and no events.

**New functions:**

```python
def dismiss_suggestion_record(
    path: Path,
    repo_name: str,
    reason: str = "",
    expires_days: int | None = None,  # NEW
) -> DismissedSuggestion:
    """... existing logic ...
    If expires_days is set, set expires_at = today + expires_days days (ISO date).
    Append a DismissalEvent of type 'dismissed' to events list."""

def expire_dismissals(path: Path, today: date | None = None) -> list[DismissedSuggestion]:
    """Walk items; remove those whose expires_at < today.
    For each expired entry, append a DismissalEvent of type 'expired' with actor='system'.
    Save atomically. Return list of expired entries."""

def load_dismissal_events(path: Path) -> list[DismissalEvent]:
    """Read events array from the file. Missing/old-schema → []."""
```

**CLI flag updates** in `src/cli.py` triage subparser:

```python
p.add_argument(
    "--dismiss-expires-days",
    type=int,
    default=None,
    metavar="N",
    help="Auto-expire dismissal after N days (default: permanent)",
)
p.add_argument(
    "--expire-dismissals",
    action="store_true",
    help="Run cleanup: remove dismissals whose expiry date has passed",
)
p.add_argument(
    "--dismissal-history",
    action="store_true",
    help="Show audit trail of dismissal events",
)
```

`_run_dismiss_suggestion_mode(args)` passes `expires_days=getattr(args, "dismiss_expires_days", None)`.

New mode functions:
- `_run_expire_dismissals_mode(args)` — calls `expire_dismissals()`, prints count + list
- `_run_dismissal_history_mode(args)` — calls `load_dismissal_events()`, prints chronological table

**`load_dismissed` updates** — when reading v1 schema, default missing fields gracefully. When reading v2, read `items` + `events` arrays. `save_dismissed` ALWAYS writes v2 (no operator action needed to migrate).

### 12.2 — Web `/initiatives/dismissed` page + Undo

**New GET route** in `src/serve/routes.py`:

```python
@router.get("/initiatives/dismissed", response_class=HTMLResponse)
async def initiatives_dismissed(request: Request) -> HTMLResponse:
    """List currently dismissed suggestions with per-row Undo button."""
    from src.suggest_initiatives import load_dismissed, dismissed_path
    
    output_dir = _output_dir(request)
    items = load_dismissed(dismissed_path(output_dir))
    
    rows = [
        {
            "repo_name": d.repo_name,
            "reason": d.reason,
            "dismissed_at": d.dismissed_at,
            "dismissed_by": d.dismissed_by,
            "expires_at": getattr(d, "expires_at", None),
        }
        for d in items
    ]
    
    return templates.TemplateResponse(
        request, "initiatives_dismissed.html",
        {"rows": rows, "count": len(rows)},
    )
```

**New POST route**:

```python
@router.post("/initiatives/dismissed/undo", response_class=HTMLResponse)
async def undo_dismiss_route(
    request: Request,
    repo_name: str = Form(...),
) -> HTMLResponse:
    """Restore a dismissed repo. HTMX swap-out the row."""
    from src.suggest_initiatives import undo_dismiss, dismissed_path
    
    output_dir = _output_dir(request)
    removed = undo_dismiss(dismissed_path(output_dir), repo_name)
    
    import html as _html
    if removed:
        return HTMLResponse(
            f'<tr class="undone"><td colspan="5">✓ Restored: {_html.escape(repo_name)}</td></tr>'
        )
    else:
        return HTMLResponse(
            f'<tr class="undo-error"><td colspan="5">Error: {_html.escape(repo_name)} not currently dismissed</td></tr>',
            status_code=404,
        )
```

**New template `src/serve/templates/initiatives_dismissed.html`** modeled after `initiatives.html` (Sprint 7A):

- Header: "Dismissed Suggestions" + count
- Empty state: "No dismissed suggestions."
- Table columns: REPO | DISMISSED AT | EXPIRES AT | REASON | ACTIONS (Undo button)
- Per-row HTMX Undo button POSTing to `/initiatives/dismissed/undo` with `hx-confirm="Restore {repo_name} to suggestion pool?"`

**Nav link** in `base.html`: add `<li><a href="/initiatives/dismissed">Dismissed</a></li>` between "Suggestions" and "New Run".

### 12.3 — Briefing dismissals section

In `src/briefing.py`:

1. Add a parameter to `build_briefing(..., output_dir: Path | None = None)` so it can load dismissed-suggestions.json. Mirror Sprint 11 pattern.
2. Add `dismissed_repos: list[str]` field to `Briefing` dataclass (`field(default_factory=list)`).
3. When `output_dir is not None`, load dismissed list via `load_dismissed(dismissed_path(output_dir))` and populate `dismissed_repos = [d.repo_name for d in items if d.expires_at is None or d.expires_at >= today]` (skip auto-expired).
4. In `render_markdown(briefing)`, add a section AFTER the "Suggested Initiatives" section (or near the end if no Suggested Initiatives present):

```markdown
## Currently Dismissed

3 repos are currently suppressed from suggestions:
- ToyProject — _too speculative_
- OldFork — _abandoned_
- ScratchPad — _no expiry_
```

If `dismissed_repos` is empty, omit the section.

Wire `output_dir` through `generate_briefing()` and the CLI invocation (in `src/cli.py` `_run_briefing_mode` or equivalent).

Tests: existing `tests/test_briefing.py`. Add ~5 cases (empty, populated, mixed expiry).

### 12.4 — `audit report --tier-gaps`

In `src/cli.py` `_build_report_subparser` (the `audit report` subcommand), add:

```python
p.add_argument(
    "--tier-gaps",
    action="store_true",
    help="Dump per-repo TierGap data as JSON (use --format markdown for human-readable)",
)
p.add_argument(
    "--tier-gaps-target",
    type=int,
    default=None,
    metavar="TIER",
    help="Override target tier for gap calculation (default: current+1 per repo)",
)
p.add_argument(
    "--format",
    choices=["json", "markdown"],
    default="json",
    help="Output format for --tier-gaps (default: json)",
)
```

New mode `_run_tier_gaps_export_mode(args)`:

1. Load portfolio-truth-latest.json.
2. For each project: `compute_tier(repo)`, then `tier_gap(repo, target_tier)` where target = `args.tier_gaps_target` or `current+1`.
3. Skip repos at current_tier=0 (no git) or current_tier=4 (Platinum, no next tier).
4. Build a JSON/markdown output:
   - JSON: `{"version": 1, "generated_at": "...", "gaps": [{"repo_name": ..., "current_tier": ..., "target_tier": ..., "missing_requirements": [...], "requirement_sources": [...]}, ...]}`
   - Markdown: a table with one row per repo, columns: REPO | CURRENT → TARGET | MISSING | SOURCE
5. Print to stdout (operator can redirect).

New module `src/tier_gaps_export.py` if it makes sense (small enough to inline if not). Tests in `tests/test_tier_gaps_export.py` or appended to `tests/test_cli_report.py`.

## Tests target

| Item | New tests |
|---|---|
| 12.1 | ~18-22 (expires_days, expire_dismissals, audit-trail event recording, schema migration v1→v2 read, CLI flags) |
| 12.2 | ~10-12 (GET dismissed page empty/populated, POST undo happy/404/HTML-escape, nav link present) |
| 12.3 | ~5-7 (briefing field populated, markdown render with/without dismissals, expired ones excluded) |
| 12.4 | ~10-15 (mode happy path, target override, JSON shape, markdown shape, missing portfolio-truth) |
| **Total** | **~45-55 new tests** |

## Exit criteria

- 12.1: `audit triage --dismiss-suggestion REPO --dismiss-expires-days 30` writes an entry with `expires_at` set. `audit triage --expire-dismissals` on a clock past the expiry removes the entry and logs an "expired" event. `audit triage --dismissal-history` prints a chronological table.
- 12.2: `GET /initiatives/dismissed` renders the dismissed table with Undo buttons. `POST /initiatives/dismissed/undo` removes the entry and returns a success row. Subsequent GET shows the entry gone. Nav link visible from any page.
- 12.3: `audit triage --briefing --include-suggestions` produces markdown containing "## Currently Dismissed" section when any non-expired dismissals exist. Section omitted when empty.
- 12.4: `audit report saagpatel --tier-gaps` prints valid JSON. `--format markdown` prints a readable table. Schema is versioned.
- All exit: 1890 → ~1945+ tests pass; ruff clean.

## Constraints

1. MUST NOT break the existing 1890 tests.
2. v2 schema must read v1 files cleanly. v1-only callers (briefing path that doesn't use `output_dir`, anything else) keep working.
3. Atomic tmp+rename for all file writes (Sprint 11 pattern).
4. Auto-expire is an explicit operator action (`--expire-dismissals`) NOT auto-run on every CLI invocation. The operator opts in.
5. Briefing dismissals section is opt-out by being part of `include_suggestions=True` path. If operator runs briefing WITHOUT `--include-suggestions`, no dismissals section either.
6. Web Undo path returns HTMX-friendly `<tr>` fragments; `hx-swap="outerHTML"` from the calling row.
7. `tier-gaps` export does NOT call the LLM (deterministic dump from portfolio-truth + maturity_tiers).
8. No new dependencies.
9. Cwd discipline preamble + "always `git add` closeout immediately" note in every subagent brief.

## Critical files

| File | Item(s) |
|---|---|
| `src/suggest_initiatives.py` | 12.1 |
| `src/cli.py` | 12.1 (triage subparser), 12.4 (report subparser) |
| `src/serve/routes.py` | 12.2 |
| `src/serve/templates/initiatives_dismissed.html` (new) | 12.2 |
| `src/serve/templates/base.html` | 12.2 (nav link) |
| `src/briefing.py` | 12.3 |
| `src/maturity_tiers.py` (read-only) | 12.4 (uses `tier_gap`) |
| `src/tier_gaps_export.py` (new, optional) | 12.4 |
| `tests/test_*.py` | all items |
| `docs/plans/2026-05-12-arc-g-sprint-12-closeout.md` (new) | 12.5 |

## Verification

```bash
cd /Users/d/Projects/GithubRepoAuditor

# 12.1 — auto-expire workflow
mkdir -p /tmp/sprint12-test/output
unset ANTHROPIC_API_KEY GITHUB_TOKEN
python3 -m src triage saagpatel --dismiss-suggestion FakeRepo --dismiss-expires-days 0 --output-dir /tmp/sprint12-test/output
python3 -m src triage saagpatel --expire-dismissals --output-dir /tmp/sprint12-test/output  # should expire it
python3 -m src triage saagpatel --dismissal-history --output-dir /tmp/sprint12-test/output

# 12.2 — web dismissed page
python3 -m src serve --port 8765 --host 127.0.0.1 &
SERVER_PID=$!; sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/initiatives/dismissed   # 200
curl -s http://127.0.0.1:8765/initiatives/dismissed | grep -c "/initiatives/dismissed/undo"   # >= 0
kill $SERVER_PID

# 12.4 — tier-gaps JSON
python3 -m src report saagpatel --tier-gaps --output-dir output 2>&1 | head -20

# Full suite
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3
python3 -m ruff check src/ tests/ 2>&1 | tail -3
```

Visual verification: `/verify` skill + Playwright MCP after Wave 1 merges.
Pre-merge: `/code-review` skill on the Sprint 12 diff.

## Out of scope

- Bulk dismiss / bulk undo from web (low operator value)
- Persistent storage for tier-gap snapshots over time (point-in-time export is enough for v1)
- Dismissed suggestions feeding back into `audit report` portfolio score (no operator demand)
- Auto-expire heuristics based on repo activity (small overlap, premature)
