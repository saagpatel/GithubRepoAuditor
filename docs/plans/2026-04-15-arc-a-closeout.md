# Arc A Closeout: Context Quality Recovery

**Date**: 2026-04-15  
**Phases**: 113-118  
**Branch**: main (Phases 113-117 operational; Phase 114 via PR #113)

---

## What Arc A Did

Deployed the `--allow-dirty-worktree` flag (Phase 114) to unblock the context recovery pipeline, then ran batch apply across all 50 eligible repos in 4 cohorts (Phases 115-116). The managed context block (`<!-- portfolio-context:start -->` markers) was written into AGENTS.md or CLAUDE.md for each target, scraping README/package.json/pyproject signals to populate 6 structured sections.

---

## Pre-Recovery Baseline (Phase 113)

| Metric | Count |
|---|---|
| Total projects | 115 |
| context: boilerplate | 88 |
| context: minimum-viable | 13 |
| context: standard | 8 |
| context: full | 4 |
| context: none | 2 |
| **risk: elevated** | **54** |
| risk: moderate | 4 |
| risk: baseline | 40 |
| risk: deferred | 17 |

Recovery plan cohort: 54 targets — 0 eligible (100% skipped as `dirty-worktree`), 2 excluded (temporary names).

---

## Post-Recovery Results (Phase 117)

| Metric | Before | After | Delta |
|---|---|---|---|
| context: boilerplate | 88 | 51 | -37 |
| context: minimum-viable | 13 | 34 | +21 |
| context: standard | 8 | 18 | +10 |
| context: full | 4 | 11 | +7 |
| context: none | 2 | 1 | -1 |
| **risk: elevated** | **54** | **16** | **-38** |
| risk: moderate | 4 | 4 | 0 |
| risk: baseline | 40 | 78 | +38 |
| risk: deferred | 17 | 17 | 0 |

**Total repos updated**: 72 (across 4 cohort runs: 20 + 20 + 20 + 12)  
**Failed**: 0  
**Skipped (ambiguous-primary-context)**: 4  
**Excluded (temporary/generated)**: 2

---

## Repos Still Elevated (16) — Manual Resolution Queue

All 16 share `investigate-override` (catalog `intended_disposition: investigate`), which is an independent elevated factor. Most also have `no-run-instructions` from context scraping.

| Repo | Factors |
|---|---|
| APIReverse | weak-context-active, investigate-override, no-run-instructions |
| ApplyKit | weak-context-active, investigate-override, no-run-instructions |
| AuraForge | weak-context-active, investigate-override, missing-operating-path, no-run-instructions |
| bridge-db | weak-context-active, investigate-override |
| da-scaffold | weak-context-active, investigate-override, missing-operating-path, no-run-instructions |
| DevToolsTranslator | weak-context-active, investigate-override, no-run-instructions |
| DNSWatcher | weak-context-active, investigate-override |
| GithubRepoAuditor | weak-context-active, investigate-override, no-run-instructions, undocumented-risks |
| IncidentMgmt | weak-context-active, investigate-override, missing-operating-path, no-run-instructions |
| IncidentReview | weak-context-active, investigate-override, no-run-instructions |
| JobCommandCenter | weak-context-active, investigate-override, no-run-instructions, undocumented-risks (ambiguous-context: has both CLAUDE.md and AGENTS.md) |
| notification-hub | weak-context-active, investigate-override, no-run-instructions |
| resume-evolver-tmp-1776063720 | weak-context-active, investigate-override, missing-operating-path, no-run-instructions (temporary name) |
| SpecCompanion | weak-context-active, investigate-override, no-run-instructions |
| thought-trails | weak-context-active, investigate-override, no-run-instructions (ambiguous-context: has both CLAUDE.md and AGENTS.md) |
| visual-album-studio | weak-context-active, investigate-override, no-run-instructions |

**Pattern**: `investigate-override` won't be resolved by context recovery — it requires either updating the catalog disposition to `maintain`/`grow` or manually downgrading activity status.

---

## Repos That Moved elevated → baseline (~38)

The full set is visible in `output/portfolio-truth-latest.json`. The `weak-context-active` factor was removed for all repos whose context quality upgraded from `boilerplate`/`none` to `minimum-viable` or above, and who did not have other elevated factors.

---

## Lessons Learned

1. **Dirty worktree was the entire blocker.** Adding `--allow-dirty-worktree` unlocked 48 repos instantly. The flag is safe: `upsert_managed_context_block` only replaces the fenced managed block, doesn't touch other file content.

2. **`investigate-override` is the next elevation floor.** 16 repos remain elevated solely because their catalog disposition is `investigate`. Context recovery cannot fix this — it requires a catalog review pass or an Arc D automated catalog update.

3. **Ambiguous-context repos (4) need manual resolution.** JobCommandCenter, thought-trails, and 2 others have both CLAUDE.md and AGENTS.md with non-trivial content. Pick one file, consolidate, then re-run recovery.

4. **Context scraping produces `minimum-viable` skeleton, not `standard`.** The `no-run-instructions` factor persists on many recovered repos because README-scraping didn't find a "How To Run" section. Operator can manually add run instructions to the managed block to resolve this.

5. **Batch size of 20 was appropriate.** 4 runs to clear 72 repos. No failures across any cohort.

---

## What Comes Next

### Arc D (Phases 119+): Safe Automation Expansion
- **Prerequisite met**: elevated count dropped from 54 → 16 (below the ~20 threshold)
- Add bounded `--auto-apply` automation for repos with `path_confidence=high` and `decision_quality=trusted`
- Key files: `src/operator_decision_quality.py`, approval center in `src/cli.py`, `config/portfolio-catalog.yaml`

### Arc E: Desktop Portfolio Shell
- Independent of Arc A — can start anytime
- Tauri 2 + React app consuming `portfolio-truth-latest.json` and `weekly-command-center-*.json`
- Repo: `JobCommandCenter`

### Arc F: Renderer Simplification
- After Arcs A+D prove parity model stable across 2+ weekly review cycles
- Shared render contract for 5 parallel surfaces (Excel, Markdown, HTML, review-pack, handoff)
