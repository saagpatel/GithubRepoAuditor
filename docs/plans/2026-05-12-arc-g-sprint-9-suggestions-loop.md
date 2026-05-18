# Arc G — Sprint 9: Suggestions → Initiative loop closure

**Status:** Drafted 2026-05-12 after Sprint 8 shipped (main `5750272`). Sprint 9 / Arc G closes the loop between LLM-ranked suggestions (8.4) and the initiative tracker (7A).

## Context

Sprint 8.4 ships `--suggest-initiatives`: the operator sees an LLM-ranked list of repos closest to qualifying for their next tier. But there's friction — the operator must then run a second command (`--set-initiative REPO --target-tier N --deadline YYYY-MM-DD`), inventing a deadline themselves. The suggestion and the commitment live in separate workflows.

Sprint 9 closes the loop:
- **9.1** — CLI `--accept-suggestion REPO` flag that converts a suggestion directly into an initiative with a sane default deadline.
- **9.2** — Web `/initiatives/suggestions` page + "Accept" button that POSTs to the same backend. Also threads `TierGap.requirement_sources` (from 8.3) into the `/initiatives` template to show "(approx.)" hints next to proxy-derived gaps.

The skipped deferred items (partial-section apply, README staleness strict signal) stay out of scope — neither carries enough operator value to justify the risk/effort.

## Inventory

| # | Item | Effort | Depends on | Status |
|---|---|---|---|---|
| 9.1 | CLI `--accept-suggestion REPO [--deadline YYYY-MM-DD]` flag + `accept_suggestion()` backend in `src/suggest_initiatives.py` | small-medium | Sprint 8 merged | ⏳ |
| 9.2 | Web route `GET /initiatives/suggestions` rendering 8.4 output + HTMX "Accept" button POSTing to `/initiatives/accept`; thread `requirement_sources` into existing `/initiatives` template | medium | 9.1 | ⏳ |
| 9.3 | Sprint 9 closeout + PR | small | 9.1-9.2 | ⏳ |

**Test count target:** 1779 → ~1820 (+35-45 new tests).

## Subagent dispatch plan

Two waves, sequential. Smaller than Sprint 8 — this is loop-closure, not new architecture.

### Wave 1 — Agent A (Sonnet, isolation: worktree)

- **Item 9.1** — backend + CLI. Independent. ~1-1.5 hr effort.

### Wave 2 — Agent B (Sonnet, isolation: worktree)

- **Item 9.2** — web route + template polish. Depends on Agent A's `accept_suggestion()` backend being merged. ~2 hr effort.

### Closeout (lead)

- **Item 9.3** — closeout doc + PR + merge.

**Subagent brief preamble (mandatory):** every brief opens with the cwd-discipline preamble from Sprint 8 retro — "Before ANY edit, run `pwd` and confirm worktree path." Wave-1 Agent B in Sprint 8 escaped its worktree; the preamble prevented further escapes.

## Schema + code references

### 9.1 — `accept_suggestion()` backend + CLI flag

**Backend in `src/suggest_initiatives.py`:**

```python
def default_deadline_for_effort(effort: str, today: date | None = None) -> str:
    """Map estimated_effort to a default deadline.
    small  → today + 14 days
    medium → today + 30 days
    large  → today + 60 days
    unknown/other → today + 30 days
    Returns YYYY-MM-DD."""

def accept_suggestion(
    repo_name: str,
    projects: list[dict],
    output_dir: Path,
    deadline: str | None = None,
    target_tier: int | None = None,
) -> Initiative:
    """Convert a suggestion into an initiative.
      1. Find project in `projects` by identity.display_name == repo_name. Raise ValueError if missing.
      2. current = compute_tier(project). Raise ValueError if current == 0 or current == 4.
      3. If target_tier is None: target = current + 1. Otherwise validate target > current.
      4. If deadline is None:
           - try to find a recent suggestion for this repo (re-run generate_suggestions or accept a passed-in
             list). Map its estimated_effort to a default deadline.
           - if no suggestion found: default 30 days.
      5. Validate deadline parses as YYYY-MM-DD and is >= today.
      6. Build Initiative(repo_name, target_tier=target, deadline, set_at=now, set_by=operator_identity()).
      7. upsert_initiative(initiatives_path(output_dir), initiative).
      8. Return the Initiative."""
```

The function is the **single backend entry point** for both CLI and web. No duplication of validation/upsert logic.

**CLI flag in `src/cli.py` `_build_triage_subparser` (around line 245, next to `--suggest-initiatives`):**

```python
p.add_argument(
    "--accept-suggestion",
    type=str,
    default=None,
    metavar="REPO",
    help="Convert a suggestion into an initiative (creates an initiatives.json entry)",
)
p.add_argument(
    "--target-tier",
    # already exists for --set-initiative — reuse it here
)
# --deadline already exists for --set-initiative — reuse
```

Dispatcher (near the existing `--set-initiative` handler):

```python
if getattr(args, "accept_suggestion", None):
    _run_accept_suggestion_mode(args)
    return
```

**Mode function `_run_accept_suggestion_mode(args)`:**

```python
def _run_accept_suggestion_mode(args) -> None:
    import json
    from pathlib import Path
    from src.suggest_initiatives import accept_suggestion
    
    truth_path = Path(args.output_dir) / "portfolio-truth-latest.json"
    if not truth_path.exists():
        print_warning("portfolio-truth-latest.json not found. Run `audit run --portfolio-truth` first.")
        return
    
    truth = json.loads(truth_path.read_text())
    projects = truth.get("projects", [])
    
    try:
        initiative = accept_suggestion(
            repo_name=args.accept_suggestion,
            projects=projects,
            output_dir=Path(args.output_dir),
            deadline=getattr(args, "deadline", None),
            target_tier=getattr(args, "target_tier", None),
        )
    except ValueError as exc:
        print_error(str(exc))
        return
    
    print_info(
        f"✓ Initiative accepted: {initiative.repo_name} → "
        f"Tier {initiative.target_tier} by {initiative.deadline}"
    )
```

### 9.2 — Web route + template polish

**New route in `src/serve/routes.py`** near the existing `/initiatives` route (which lives near line 350 after Sprint 7A):

```python
@router.get("/initiatives/suggestions", response_class=HTMLResponse)
async def initiatives_suggestions(
    request: Request,
    target: int | None = None,
) -> HTMLResponse:
    """Render LLM-ranked suggestions as a page with per-card Accept buttons.
    `target` query param overrides per-repo next-tier targeting."""
    from src.suggest_initiatives import generate_suggestions
    
    output_dir = _output_dir(request)
    truth_path = output_dir / "portfolio-truth-latest.json"
    if not truth_path.exists():
        return templates.TemplateResponse(
            request, "initiatives_suggestions.html",
            {"suggestions": [], "error": "portfolio-truth-latest.json not found"},
            status_code=200,
        )
    
    import json
    truth = json.loads(truth_path.read_text())
    projects = truth.get("projects", [])
    
    suggestions, cost = generate_suggestions(projects, target_tier=target, budget_usd=0.10)
    
    rows = [
        {
            "repo_name": s.repo_name,
            "current_tier": s.current_tier,
            "current_tier_name": tier_name(s.current_tier),
            "target_tier": s.target_tier,
            "target_tier_name": tier_name(s.target_tier),
            "missing_requirements": s.missing_requirements,
            "rationale": s.rationale,
            "estimated_effort": s.estimated_effort,
            "default_deadline": default_deadline_for_effort(s.estimated_effort),
        }
        for s in suggestions
    ]
    
    return templates.TemplateResponse(
        request, "initiatives_suggestions.html",
        {"suggestions": rows, "cost_usd": cost, "error": None},
    )


@router.post("/initiatives/accept", response_class=HTMLResponse)
async def accept_initiative_route(
    request: Request,
    repo_name: str = Form(...),
    target_tier: int = Form(...),
    deadline: str = Form(...),
) -> HTMLResponse:
    """HTMX endpoint: convert suggestion into initiative. Returns updated card partial."""
    from src.suggest_initiatives import accept_suggestion
    
    output_dir = _output_dir(request)
    truth = json.loads((output_dir / "portfolio-truth-latest.json").read_text())
    projects = truth.get("projects", [])
    
    try:
        initiative = accept_suggestion(
            repo_name=repo_name, projects=projects, output_dir=output_dir,
            deadline=deadline, target_tier=target_tier,
        )
    except ValueError as exc:
        return HTMLResponse(
            f'<div class="suggestion-card accept-error">Error: {exc}</div>',
            status_code=400,
        )
    
    return HTMLResponse(
        f'<div class="suggestion-card accepted">'
        f'✓ Accepted: {initiative.repo_name} → Tier {initiative.target_tier} '
        f'by {initiative.deadline}. '
        f'<a href="/initiatives">View initiatives</a>'
        f'</div>'
    )
```

**New template `src/serve/templates/initiatives_suggestions.html`** extends `base.html`:

```html
{% block content %}
<h1>Suggested Initiatives</h1>

{% if error %}
<div class="empty-state">{{ error }}</div>
{% elif not suggestions %}
<div class="empty-state">
  No suggestions: all repos either already qualify for their next tier or have too many missing requirements.
</div>
{% else %}
<p class="meta">
  {{ suggestions|length }} suggestion(s) · LLM cost ${{ "%.4f"|format(cost_usd) }}
</p>

{% for s in suggestions %}
<div class="suggestion-card" id="suggestion-{{ loop.index }}">
  <h3>{{ s.repo_name }}</h3>
  <p class="meta">{{ s.current_tier_name }} → {{ s.target_tier_name }} · [{{ s.estimated_effort }}]</p>
  <p>{{ s.rationale }}</p>
  <details>
    <summary>Missing requirements ({{ s.missing_requirements|length }})</summary>
    <ul>{% for r in s.missing_requirements %}<li>{{ r }}</li>{% endfor %}</ul>
  </details>
  
  <form
    hx-post="/initiatives/accept"
    hx-target="#suggestion-{{ loop.index }}"
    hx-swap="outerHTML"
    class="accept-form"
  >
    <input type="hidden" name="repo_name" value="{{ s.repo_name }}">
    <input type="hidden" name="target_tier" value="{{ s.target_tier }}">
    <label>
      Deadline: <input type="date" name="deadline" value="{{ s.default_deadline }}" required>
    </label>
    <button type="submit">Accept</button>
  </form>
</div>
{% endfor %}
{% endif %}
{% endblock %}
```

**Nav link** in `src/serve/templates/base.html`: add `<li><a href="/initiatives/suggestions">Suggestions</a></li>` between "Initiatives" and "New Run".

**Threading `requirement_sources` into `/initiatives` template:**

In `src/serve/routes.py` the existing `/initiatives` handler builds rows from `tier_gap(repo, init.target_tier)`. The handler already has access to `gap.missing_requirements`; it just doesn't pass through `gap.requirement_sources` yet (added by Sprint 8.3 to `TierGap`).

Change:
```python
rows.append({
    ...,
    "missing_requirements": gap.missing_requirements if gap else [],
    "requirement_sources": gap.requirement_sources if gap else [],  # NEW
    ...,
})
```

In `src/serve/templates/initiatives.html` (and `initiative_gap.html`) where missing requirements are iterated, render the source hint:

```html
{% for req in row.missing_requirements %}
  <li>
    {{ req }}
    {% if loop.index0 < row.requirement_sources|length and row.requirement_sources[loop.index0] == "proxy" %}
      <span class="approx-hint">(approx.)</span>
    {% endif %}
  </li>
{% endfor %}
```

Minimal CSS for `.approx-hint`: muted color (`color: var(--text-muted)` or `#888`), smaller font-size.

## Tests target

| Item | New tests |
|---|---|
| 9.1 | ~15-20 (default_deadline_for_effort mapping, accept_suggestion happy/error paths, CLI flag parsing + dispatch, idempotent re-accept) |
| 9.2 | ~15-20 (route happy/empty/error, accept POST happy/validation-error, requirement_sources rendered correctly in /initiatives, nav link present) |
| **Total** | **~30-40 new tests** |

## Exit criteria

- 9.1: `audit triage saagpatel --accept-suggestion Wavelength` creates an initiative for Wavelength at the next-tier-up with a default deadline mapped from the most recent suggestion's `estimated_effort`. The CLI prints a confirmation line and `output/initiatives.json` carries the new entry.
- 9.1: `--accept-suggestion REPO --deadline 2026-06-15 --target-tier 3` overrides defaults.
- 9.1: `--accept-suggestion REPO_NOT_IN_TRUTH` fails cleanly with a clear error message and exit code 2.
- 9.2: `GET /initiatives/suggestions` renders N suggestion cards (or empty state). Each card has an Accept form with the default-deadline date input pre-filled.
- 9.2: `POST /initiatives/accept` with valid form data writes to `initiatives.json` and returns an HTMX partial showing "✓ Accepted".
- 9.2: `POST /initiatives/accept` with invalid `repo_name` returns 400 + error partial.
- 9.2: `/initiatives` page shows `(approx.)` hint next to proxy-derived gaps. Strict-derived gaps render without the hint.
- All exit: 1779 → ~1820+ tests pass; ruff clean; boot test green on `/initiatives/suggestions` (200) + `/initiatives/accept` POST.

## Constraints (hard)

1. **MUST NOT break existing 1779 tests.** All changes are additive.
2. **`accept_suggestion()` is the single backend entry point** for both CLI and web. No duplicated validation/upsert logic.
3. **Cwd discipline preamble** in every subagent brief (Sprint 8 lesson — Wave-1 Agent B escaped its worktree).
4. **No new dependencies.**
5. **Default deadline mapping is a single source of truth** (`default_deadline_for_effort()`). Both CLI and web use it.
6. **Don't auto-create initiatives WITHOUT operator action.** The accept flow always requires either a CLI invocation or a web button click. No silent writes to `initiatives.json` from `generate_suggestions()`.
7. **Re-accepting an existing initiative is idempotent.** `upsert_initiative()` replaces by repo_name; if the operator re-accepts with different target/deadline, the old entry is overwritten cleanly. No duplicate entries.

## Critical files

| File | Item(s) touching it |
|---|---|
| `src/suggest_initiatives.py` | 9.1 (adds `accept_suggestion`, `default_deadline_for_effort`) |
| `src/cli.py` | 9.1 (flag + dispatcher + mode function) |
| `src/initiatives.py` (read-only) | 9.1 (reuses `upsert_initiative`, `operator_identity`) |
| `src/maturity_tiers.py` (read-only) | 9.1 (`compute_tier` validation), 9.2 (`requirement_sources` already populated) |
| `src/serve/routes.py` | 9.2 (two new routes) |
| `src/serve/templates/initiatives_suggestions.html` (new) | 9.2 |
| `src/serve/templates/base.html` | 9.2 (nav link) |
| `src/serve/templates/initiatives.html` | 9.2 (requirement_sources hint) |
| `src/serve/templates/initiative_gap.html` | 9.2 (requirement_sources hint) |
| `tests/test_suggest_initiatives.py` (extended) | 9.1 |
| `tests/test_initiatives_suggestions_route.py` (new) | 9.2 |
| `docs/plans/2026-05-12-arc-g-sprint-9-suggestions-loop.md` | 9.3 (closeout) |

## Verification

End-to-end after both items merge:

```bash
cd /Users/d/Projects/GithubRepoAuditor

# 9.1 — CLI accept flow
python3 -m src triage saagpatel --suggest-initiatives 2>&1 | head -10
# Pick a repo from the output, then:
python3 -m src triage saagpatel --accept-suggestion <REPO>
# Expect: ✓ Initiative accepted: <REPO> → Tier N by YYYY-MM-DD
python3 -c "
import json
d = json.load(open('output/initiatives.json'))
print(d['initiatives'])
"
# Expect: the accepted initiative appears

# 9.2 — Web suggestions + accept
python3 -m src serve --port 8765 --host 127.0.0.1 &
SERVER_PID=$!
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/initiatives/suggestions   # 200
curl -s http://127.0.0.1:8765/initiatives/suggestions | grep -c "suggestion-card"          # N >= 0
# Accept via POST (use a real repo name from the page):
curl -s -X POST http://127.0.0.1:8765/initiatives/accept \
  -d "repo_name=<REPO>" -d "target_tier=2" -d "deadline=2026-06-30" -w "\n%{http_code}\n"
# Expect: HTML fragment + 200

# Verify requirement_sources hints visible:
curl -s http://127.0.0.1:8765/initiatives | grep -c "approx"
# Expect: >= 1 if any proxy-derived gaps exist

kill $SERVER_PID

# Full suite
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3   # expect ~1820+ passed
python3 -m ruff check src/ tests/ 2>&1 | tail -3                  # All checks passed!
```

Visual verification (after Wave 2 lands): use `/verify` skill with Playwright MCP to screenshot `/initiatives/suggestions`, click an Accept button, confirm the partial swap shows the success state.

Pre-merge: invoke `/code-review` skill on the full Sprint 9 diff if it exceeds 200 LoC (likely will, given the new template).

## Out of scope (deferred to Sprint 10 or beyond)

- Partial-section apply for draft-readmes (still risky — produces broken READMEs)
- README staleness strict signal (proxy works fine; no leverage)
- Bulk-accept ("Accept all suggestions" button) — premature, would mask per-suggestion review
- Auto-suggest-on-briefing-render — Sprint 8 already gated this behind `--include-suggestions` flag for cost reasons; keep as-is
- "Reject suggestion" workflow that suppresses a repo from future suggestions — defer until we have operator feedback that suggestions are too noisy

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| `generate_suggestions()` cost spikes when `/initiatives/suggestions` is hit by browser refresh | Default $0.10 budget on the route call. Future: cache suggestions for N minutes if cost becomes an issue. |
| Operator accepts a stale suggestion (current_tier changed since suggestion generated) | `accept_suggestion()` re-validates `target > current` at write time; raises ValueError if no longer applicable. |
| Two operators racing to accept the same suggestion | `upsert_initiative()` is last-write-wins by `repo_name`. Acceptable for single-operator use case (which is the only deployment shape today). |
| Web "Accept" succeeds but `initiatives.json` write fails on disk | The atomic tmp+rename pattern in `save_initiatives()` (Sprint 7A) ensures we never half-write. On disk error, the route returns 400 + the operator can retry. |
