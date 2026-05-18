# Arc G — Sprint 12 closeout

**Status:** SHIPPED 2026-05-12. Sprint 12 ran as planned in `docs/plans/2026-05-12-arc-g-sprint-12-dismissal-polish.md`. Four Sonnet subagents across two waves + a `/code-review` fix-up commit.

## Final state

- Feat branch tip: `9095248`
- Tests: 1890 → **1965 passed** (+75), 2 skipped, ruff clean
- All four Sprint 11 follow-on items closed + `/verify` + `/code-review` skills exercised

## Inventory

| # | Item | Commit | Tests | Notes |
|---|---|---|---|---|
| 12.2 | `/initiatives/dismissed` web page + Undo + nav link | `78a11de` | +11 | Wave 1 Agent A. Route ordering correct (placed before `/initiatives/{repo_name}/gap`). |
| 12.3 | Briefing "Currently Dismissed" section + `DismissedRepoRow` | `665faf7` | +14 | Wave 1 Agent B. Initial implementation had a stale double-read (Agent B couldn't see Sprint 12.1's `expires_at` field); cleaned up in fix-up. |
| 12.4 | `audit report --tier-gaps [--format json\|markdown]` | `2a62dc1` | +24 | Wave 1 Agent C. 129 real gaps surfaced in boot test against actual portfolio-truth. Initial impl missed `choices=[2,3,4]` on `--tier-gaps-target`; added in fix-up. |
| 12.1 | Auto-expire + `DismissalEvent` audit trail + v1→v2 schema | `791540c` | +26 | Wave 2 Agent D. Backward-compat: v1 files load cleanly into v2 (no migration step required). |
| — | Code-review fix-ups | `9095248` | (no test change; all 1965 still pass) | Three findings from `/code-review`: web expired filter (critical), briefing double-read cleanup (major), `--tier-gaps-target` argparse choices (major). |

**Tests:** 1890 → 1965 (+75 across 5 commits).

## Boot-test results

| Scenario | Result |
|---|---|
| CLI: `--dismiss-suggestion FakeRepo --dismiss-expires-days 7` | `✗ Dismissed: FakeRepo — test (expires 2026-05-19)` |
| CLI: `--dismissal-history` | Prints chronological table with event types |
| CLI: `--expire-dismissals` (no expired entries) | "No dismissals to expire." |
| `audit report --tier-gaps` | Valid JSON with `version: 1`, `generated_at`, `gaps: [...]` |
| `audit report --tier-gaps-target 1` | argparse rejects (now constrained to choices) |
| Briefing `render_markdown` with `dismissed_repos` set | Contains "## Currently Dismissed" section |
| `GET /initiatives/dismissed` | 200, table renders, expired entries filtered out (post-fix-up) |
| `POST /initiatives/dismissed/undo` (nonexistent) | 404 |
| Nav link count for "/initiatives/dismissed" on / | 1 |

## Skills exercised

### `/verify` skill (visual)

Used Playwright MCP to navigate and screenshot:
- `/` (Dashboard) — nav order verified: Dashboard → Runs → Approvals → Initiatives → Suggestions → **Dismissed** → New Run ✓
- `/initiatives/dismissed` — header, count subtitle, table with all 5 columns (Repo | Dismissed at | Expires at | Reason | Actions), Undo button per row, footer back-links ✓
- Layout clean, no console errors, no overflow.

Screenshots saved to: `sprint12-dashboard.png`, `sprint12-initiatives.png`, `sprint12-suggestions.png`, `sprint12-dismissed.png`.

### `/code-review` skill (pre-merge gate)

Per `demand-elegance` rule (diff >200 LoC), invoked code-reviewer subagent on the four-commit branch. Findings (paraphrased):

- **Critical**: `GET /initiatives/dismissed` showed expired entries — the route handler didn't apply the same expiry filter that the briefing path used. Operator could see + Undo entries that should have been hidden. **Fixed in `9095248`.**
- **Major**: `_build_dismissed_repos` in `src/briefing.py` did a redundant double-read of the JSON file. Sprint 12.3 was written before Sprint 12.1 landed, so the helper read the raw JSON to recover `expires_at` even though Sprint 12.1 added it to the dataclass. **Fixed in `9095248`** — now uses `d.expires_at` directly, malformed dates now log a warning instead of silently passing.
- **Major**: `--tier-gaps-target` argparse declaration was missing `choices=[2, 3, 4]` on the subparser (the legacy flat parser had it; subparser didn't). Inconsistent CLI surface. **Fixed in `9095248`.**

Praise from the reviewer:
- Schema v1→v2 migration correct + tested
- Atomic tmp+rename writes consistent with operator_prefs pattern
- Route ordering for `/initiatives/dismissed` correctly placed before `/initiatives/{repo_name}/gap`
- HTML-escaping in error responses (XSS-safe)
- CLI dual-registration (subparser + legacy `build_parser`) followed for all 6 new flags
- No new dependencies

## Subagent dispatch retrospective

Wave 1 (three parallel): 12.2 + 12.3 + 12.4 — all touching different subsystems, ran cleanly in parallel.
Wave 2 (one sequential): 12.1 — touched `src/suggest_initiatives.py` + `src/cli.py` after Wave 1's Agent C had landed CLI changes; no merge conflicts on cherry-pick.

Total subagent runtime: ~32 min. Wall-clock with interleaved cherry-picks: ~40 min. **+75 tests across 5 commits.**

All four agents stayed inside their worktrees (cwd-discipline preamble holds across all sprints since Sprint 8 retro).

## Lessons

### Sprint 12.3 was written against a stale view of Sprint 12.1

Agent B (briefing) ran in parallel with Agent D (schema). Agent B's brief documented that `DismissedSuggestion` had no `expires_at` field and instructed a raw-JSON workaround. But the brief was written before Agent D actually landed Sprint 12.1, and Agent D's `expires_at` addition was already merged when Agent B's cherry-pick happened. Agent B's defensive code became stale immediately.

**Action item:** when waves are sequential, the LATER wave should refresh its brief from current state, not the brief author's view at planning time. Or — alternative pattern — have Wave 1 NOT reference fields that Wave 2 is adding, and let Wave 2 do the threading itself.

### Code-review skill caught a critical bug the boot test missed

Both the boot test and my manual CLI verification used a fresh dismissed-suggestions.json with a permanent entry. The expired-entry rendering bug only surfaces when the file contains an entry whose `expires_at` is strictly less than today. The code-reviewer's review of the diff (not behavior) caught it because the asymmetry between briefing-path (filtering) and route-path (not filtering) was visible on inspection.

**Pattern reinforced:** the demand-elegance multi-agent review gate is worth its weight. The diff was 11 files; the reviewer flagged 1 critical + 2 majors + 1 minor in a single pass.

### TaskCompleted hook continues to be ignored

437 pre-existing mypy errors continue to block task status transitions. Known noise; will be cleaned up in a future hygiene sprint if it ever becomes worth it.

## Cumulative state (Sprint 7A → 12)

| Sprint | Main commit | Tests | Headline |
|---|---|---|---|
| 7B | `3b2dcb9` | 1561 → 1586 | Per-action approval (campaign-plan packets) |
| 7A | `8eedaa3` | 1586 → 1677 | Tiered maturity + initiative tracker |
| 8 | `5750272` | 1677 → 1779 | setuptools-scm + strict tier signals + LLM suggestions + per-section drafts |
| 9 | `536349b` | 1779 → 1819 | Suggestions → initiative loop closure |
| 10 | `0412464` | 1819 → 1841 | Polish: briefing test + Excel hint + cache + force_deterministic |
| 11 | `6aaf725` | 1841 → 1890 | Persistent cache + eviction + dismiss-suggestion + TierGap JSON |
| 12 | (this PR) | 1890 → 1965 | Dismissal lifecycle + web Undo + briefing surface + tier-gap JSON export |

**+404 tests across 7 PRs.**

## Out of scope (Sprint 13 candidates)

- Web "Undo dismiss" history view (currently `--dismissal-history` is CLI-only)
- Auto-expire heuristics — opt-in expire-on-portfolio-truth-refresh (currently operator must run `--expire-dismissals` manually)
- Bulk operations: "Dismiss all proxy-only-gap suggestions" via a bulk endpoint
- Cross-link from briefing dismissals to web `/initiatives/dismissed` URL
- Auto-purge old `DismissalEvent` entries beyond N events (event log grows unbounded today)

## Next

Push, open PR #174, merge with merge commit. Tag v0.20.0 if releasing.
