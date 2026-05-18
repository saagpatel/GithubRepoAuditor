# Arc G — Sprint 13 closeout

**Status:** SHIPPED 2026-05-12. Sprint 13 ran as planned in `docs/plans/2026-05-12-arc-g-sprint-13-dismissal-followons.md`. One Haiku scope agent (Wave 1) + three parallel Sonnet subagents (Wave 2) + a `/code-review` fix-up commit + visual `/verify` pass.

## Final state

- Feat branch tip: `848c0a0`
- Tests: 1965 → **1997 passed** (+32), 2 skipped, ruff clean
- All four Sprint 12 follow-on items closed

## Inventory

| # | Item | Commit | Tests | Notes |
|---|---|---|---|---|
| 13.3 | Briefing cross-link to web pages | `3d6f308` | +5 | Wave 2 Agent C. One-line addition inside `if dismissed_repos:` block. `render_voice` left untouched. |
| 13.1 | `/initiatives/dismissal-history` web view | `8d38340` | +8 | Wave 2 Agent A. Route declared before parametric `/initiatives/{repo_name}/gap`. Event-type CSS allowlist added in fix-up. |
| 13.2 + 13.4 | Bounded event log + cache TTL | `5ddaeb5` | +19 | Wave 2 Agent B. `_MAX_DISMISSAL_EVENTS=1000`, `_CACHE_TTL_DAYS=30`, cache schema v1 → v2 (entries gain `timestamp`). v1 entries dropped on first v2 load with INFO log — operators will see one cold-cache load if upgrading from a pre-Sprint-13 file. |
| — | Code-review fix-ups | `a0f10cb` + `848c0a0` | (no test count change) | Two findings from `/code-review`: trim-cap off-by-one (Important) + CSS class injection vector (Important). Plus a chore commit removing Sprint 12 verify artifacts accidentally swept in. |

**Tests:** 1965 → 1997 (+32 across 5 commits).

## Boot-test results

| Scenario | Result |
|---|---|
| `GET /initiatives/dismissal-history` | 200, empty-state renders cleanly |
| `GET /initiatives/dismissed` | 200, includes new "View dismissal history →" footer link |
| Briefing markdown with `dismissed_repos` set | Contains `/initiatives/dismissed` and `/initiatives/dismissal-history` paths |
| `_MAX_DISMISSAL_EVENTS = 1000` (sentinel-inclusive) | Writing 1005 events ⇒ on-disk size exactly 1000 (999 newest + 1 sentinel) |
| `_CACHE_TTL_DAYS = 30` | v2 entries strictly older than 30 days are dropped on load; file rewritten atomically only when something changed |
| v1 cache file load | Returns empty cache, logs at INFO, next save promotes to v2 |

## Skills exercised

### `/code-review` skill (pre-merge gate)

Per `demand-elegance` rule (diff >200 LoC — Sprint 13 came in at ~1066 insertions across 11 files), invoked code-reviewer subagent on the four-commit branch. Findings (confidence in parentheses):

- **Important (86)**: `_save_dismissed_full` trim arithmetic produced 1001 entries after each trim, not 1000. The sentinel was appended AFTER keeping the newest `_MAX_DISMISSAL_EVENTS` events, so the file grew by 1 each trim cycle and never settled at the cap. **Fixed in `a0f10cb`** — reserve a slot for the sentinel (`keep_count = _MAX - 1`); tests updated to match the new sentinel-inclusive semantics.
- **Important (82)**: `initiatives_dismissal_history.html` interpolated `row.event_type` directly into a `class="..."` attribute. While today the value originates from application code (not operator input), a corrupted JSON file could break out of the class context (Jinja's default autoescape doesn't cover HTML-attribute injection). **Fixed in `a0f10cb`** — switched to a Jinja allowlist lookup that falls back to `event-unknown` for unrecognized values. Also added the `event-log_trimmed` and `event-unknown` CSS classes.
- **Minor (77, below report threshold)**: No test coverage for the v1-cache-drop migration path. Noted as a small follow-up but not blocking.

Praise from the reviewer:
- Route ordering correct (`dismissal-history` before `{repo_name}/gap`)
- Atomic tmp+rename pattern consistent across new write paths
- Sprint 12.1 v1→v2 roundtrip preserved (load v1, save v2, items lossless)
- TTL boundary semantics explicit + tested (exactly-TTL kept, TTL+1 dropped)
- Briefing cross-link correctly placed inside `if dismissed_repos:` guard
- XSS clean for text-content fields (Jinja default autoescape handles `repo_name`, `reason`, `actor`)
- No new dependencies
- `render_voice` untouched as specified

### `/verify` skill (visual)

Used Playwright MCP to navigate and screenshot:
- `/initiatives/dismissal-history` — empty state: heading "Dismissal History", "0 events recorded" subtitle, "No dismissal events recorded." message, back-links to Dismissed Suggestions + Suggestions ✓
- `/initiatives/dismissed` — confirms new "View dismissal history →" footer link rendered alongside existing back-links ✓
- Nav structure intact: Dashboard → Runs → Approvals → Initiatives → Suggestions → Dismissed → New Run ✓

Screenshots saved to: `sprint13-dismissal-history.png`, `sprint13-dismissed-with-history-link.png`.

## Subagent dispatch retrospective

Wave 1 (one Haiku, ~2 min): scope confirmation flagged ONE material discrepancy before Wave 2 — the persistent cache schema didn't have a `timestamp` field, so 13.4 required a v1 → v2 schema bump rather than a bolt-on TTL. Briefing for Agent B updated accordingly. Without the scope agent, Agent B would have hit this mid-implementation and either added the field silently or asked back, costing a round-trip.

Wave 2 (three parallel Sonnets, ~7 min wall clock):
- Agent A (13.1): 8 tests, no surprises
- Agent B (13.2 + 13.4): 19 tests, schema v1 → v2 clean
- Agent C (13.3): 5 tests, single-line addition

All three landed first-try with no merge conflicts on cherry-pick (different files: routes.py + template, suggest_initiatives.py + new tests, briefing.py only). The "Agent B owns both 13.2 + 13.4 to avoid conflicts" decision was correct — both items touch `src/suggest_initiatives.py` extensively.

Total subagent runtime: ~13 min. Wall-clock with code-review + verify + closeout: ~35 min.

## Lessons

### Trim-with-sentinel arithmetic is a known foot-gun

Sprint 13.2 documented the cap as `_MAX_DISMISSAL_EVENTS` and the spec said "sentinel counts toward the cap going forward", but Agent B's implementation kept `_MAX` events of history THEN appended the sentinel, ending at `_MAX + 1`. The unit test asserted `len == _MAX + 1`, locking in the bug. The code-reviewer caught this on the diff in seconds because the asymmetry between the loop invariant ("we have N+1 after trim") and the constant name (`_MAX = N`) was apparent on inspection — but the test author didn't see it because they wrote the test against the implementation, not against the spec.

**Action item:** when reserving room for a sentinel/header/footer in a bounded structure, name the visible-to-disk constant accordingly (`_MAX_DISMISSAL_EVENTS` is fine as a sentinel-inclusive cap) AND write at least one test that asserts the on-disk count matches the constant, not `constant + N`. The reviewer's "your test validates the bug" framing was sharp.

### CSS class injection is not covered by Jinja's default autoescape

The reviewer flagged that `class="event-{{ row.event_type }}"` is not safe under Jinja's HTML autoescape (which protects text content but doesn't constrain attribute values). The fix (Jinja allowlist lookup) is cheap and reusable. Worth remembering for future templates that interpolate enum-like values into class/id/data-* attributes.

**Pattern:** for any class/id/data-* attribute that takes its value from operator data (even data we wrote into the file), use an allowlist:
```jinja2
{% set _allowed = ['a', 'b', 'c'] %}
{% set _class = 'prefix-' ~ value if value in _allowed else 'prefix-unknown' %}
<span class="{{ _class }}">{{ value }}</span>
```

### Wave 1 Haiku scope agent earned its 2 minutes

The cache-schema gap (no `timestamp` field) would have cost a round-trip if Agent B had discovered it mid-implementation. A 2-minute read-only scope sweep BEFORE the parallel write wave is cheap insurance. Pattern worth keeping: use Haiku read-only scope agents whenever a plan was drafted before the latest main state was deeply read.

### TaskCompleted hook mypy noise persists

437 pre-existing mypy errors in `tests/test_briefing.py` (NarrativeProvider Protocol vs `**kwargs: Any` mismatch) continue to block task status transitions through the entire Arc G run. Known noise; cleanup is a candidate for a future hygiene sprint.

## Cumulative state (Sprint 7A → 13)

| Sprint | Main commit | Tests | Headline |
|---|---|---|---|
| 7B | `3b2dcb9` | 1561 → 1586 | Per-action approval (campaign-plan packets) |
| 7A | `8eedaa3` | 1586 → 1677 | Tiered maturity + initiative tracker |
| 8 | `5750272` | 1677 → 1779 | setuptools-scm + strict tier signals + LLM suggestions + per-section drafts |
| 9 | `536349b` | 1779 → 1819 | Suggestions → initiative loop closure |
| 10 | `0412464` | 1819 → 1841 | Polish: briefing test + Excel hint + cache + force_deterministic |
| 11 | `6aaf725` | 1841 → 1890 | Persistent cache + eviction + dismiss-suggestion + TierGap JSON |
| 12 | `cc86269` | 1890 → 1965 | Dismissal lifecycle + web Undo + briefing surface + tier-gap JSON export |
| 13 | (this PR) | 1965 → 1997 | Dismissal-history web view + bounded event log + cache TTL + briefing cross-link |

**+436 tests across 8 PRs.**

## Out of scope (Sprint 14 candidates)

- Bulk dismiss / bulk undo from web (still low operator value)
- CLI flags for `_MAX_DISMISSAL_EVENTS` and `_CACHE_TTL_DAYS` (no operator demand yet — revisit if asked)
- Auto-expire heuristics tied to repo activity
- v1-cache-drop test coverage (the Minor finding under threshold — Sprint 14 hygiene if anyone touches that code)
- Tier-gap snapshots over time (persistent point-in-time export)
- Dismissal event search / filtering on the new history page

## Next

Push, open PR, merge with merge commit. No tag — Sprint 13 is a follow-on polish PR, doesn't warrant a version bump.
