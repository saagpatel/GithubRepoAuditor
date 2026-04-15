# Arc D Closeout: Safe Automation Expansion

**Date**: 2026-04-15  
**Phases**: 119-122  
**Branch**: main (Phases 119 operational; Phases 120-122 via PRs)

---

## What Arc D Did

Built the bounded automation infrastructure — transitioning the system from purely advisory to bounded-automation with an explicit trust bar. Operator remains in the loop via catalog opt-in and approval workflow; the system now has the plumbing to execute approved packets automatically when all three trust gates pass.

---

## Phase Summary

| Phase | Type | Deliverable |
|---|---|---|
| 119 | Operational | Manual context enrichment for 16 remaining elevated repos |
| 120 | Code | `automation_eligible` field in catalog + truth model |
| 121 | Code | `--auto-apply-approved` CLI flag + `src/auto_apply.py` trust bar module |
| 122 | Code | `AUTHORITY_CAP` → `bounded-automation`; `auto-apply-safe` posture added |

---

## Trust Bar Definition

For a repo to receive automated writes via `--auto-apply-approved`:

1. **`automation_eligible: true`** — explicit catalog opt-in per repo (default `false`)
2. **`risk_tier: "baseline"`** — from the latest truth snapshot (per repo)
3. **`decision_quality_status: "trusted"`** — from operator summary (portfolio-level gate)

All three must pass. Any failure excludes the repo from auto-apply.

Safe mutation targets (allowlist): `github-topics`, `github-custom-properties`, `github-issue`, `notion-action`.  
Excluded: `github-project-item`, `github-project-fields` (modify shared project boards).

---

## Code Changes

### New: `src/auto_apply.py`
- `build_trust_bar_index(truth_snapshot, decision_quality_status)` — builds `{repo_name: bool}` index
- `get_approved_manual_campaigns(ledger_bundle)` — finds `approved-manual` campaign records
- `filter_safe_actions(actions)` — allowlist filter on mutation_target
- `filter_trusted_repo_actions(actions, trust_bar_index)` — per-repo trust bar filter

### Modified: `src/portfolio_catalog.py`
- Added `automation_eligible: bool` field (default `false`, parsed from YAML)

### Modified: `src/portfolio_truth_types.py`
- Added `automation_eligible: bool = False` to `DeclaredFields`

### Modified: `src/portfolio_truth_reconcile.py`
- Threads `automation_eligible` from catalog entry into `DeclaredFields`

### Modified: `src/cli.py`
- Added `--auto-apply-approved` flag with mutual exclusion against `--writeback-apply`, `--approve-packet`, `--campaign`
- Added `_run_auto_apply_approved_mode()` handler

### Modified: `src/action_sync_automation.py`
- Added `"auto-apply-safe": 4` to `AUTOMATION_PRIORITY` (sits between `apply-manual` and `follow-up-safe`)
- Shifted `follow-up-safe` → 5, `quiet-safe` → 6

### Modified: 3 `AUTHORITY_CAP` constants
- `src/operator_decision_quality.py`: `"advisory-only"` → `"bounded-automation"`
- `src/portfolio_risk.py`: `"advisory-only"` → `"bounded-automation"`
- `src/weekly_command_center.py`: `"report-only"` → `"bounded-automation"`

Note: `AUTHORITY_CAP` is decorative metadata for operator review surfaces — not a runtime execution gate. The actual write gate remains `args.writeback_apply` in cli.py.

---

## Test Coverage

- `tests/test_auto_apply.py` — 17 tests covering trust bar, action filtering, campaign selection
- `tests/test_portfolio_catalog.py` — 2 new tests for `automation_eligible` parsing
- `tests/test_portfolio_truth.py` — 1 new assertion that `automation_eligible` appears in truth snapshot

Total test count after Arc D: **828 tests** (up from 809 at Arc A start).

---

## What Phase 123 Needs

Phase 123 (first automated run) requires:
1. Phase 119 complete — elevated count ≤4
2. Phases 120-122 on main
3. At least 2-3 repos with `automation_eligible: true` in `config/portfolio-catalog.yaml`
4. At least 1 approved-manual campaign packet targeting those repos

See the Phase 123 section in `docs/plans/shimmying-tinkering-rocket.md` for the full runbook.

---

## Forward Arcs

### Arc E: Desktop Portfolio Shell
- Tauri 2 + React desktop app consuming `portfolio-truth-latest.json` and `weekly-command-center-*.json`
- Repo: `JobCommandCenter`
- Key surfaces: risk tier dashboard, approval queue, weekly command center, context quality heatmap

### Arc F: Renderer Simplification
- Shared render contract for 5 parallel surfaces (Excel, Markdown, HTML, review-pack, handoff)
- Prerequisite: stable schema (no new fields for 2+ weekly review cycles)
- Highest regression risk of any arc

### Arc G: Catalog Auto-Maintenance
- Expand automation to catalog-level mutations (auto-updating `intended_disposition`, `lifecycle`, `doctor_standard`)
- Gate: operator approval per batch, not per repo
- Prerequisite: Arc D proven safe at small scale across ≥3 automated runs
