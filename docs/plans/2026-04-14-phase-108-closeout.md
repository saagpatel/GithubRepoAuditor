# Phase 108 Closeout: Risk Overlay + Cross-Repo Doctor Standard

## Review Of What Was Built

Phase 108 adds a structured portfolio risk overlay and a minimal doctor/release-check standard for strategic repos. The overlay is advisory-only — it derives from already-present truth fields and does not widen any automation or approval authority.

**Core modules:**
- `src/portfolio_risk.py` (new) — owns risk tier derivation. `build_risk_entry()` accumulates up to six risk factors (`weak-context-active`, `investigate-override`, `missing-operating-path`, `missing-doctor-standard`, `no-run-instructions`, `undocumented-risks`), derives tiers (`elevated`, `moderate`, `baseline`, `deferred`), and returns a flat dict matching `RiskFields`. `build_portfolio_risk_summary()` aggregates tier counts.

**Truth schema (0.3.0 → 0.4.0):**
- `RiskFields` dataclass added to `PortfolioTruthProject` (parallel to `advisory`).
- `declared.doctor_standard` added to `DeclaredFields` (catalog intent, like `operating_path`).
- `VALID_RISK_TIERS` and `VALID_DOCTOR_STANDARDS` constant sets added to `portfolio_truth_types.py`.

**Catalog enrichment:**
- 5 strategic repos in `portfolio-catalog.yaml` now carry `doctor_standard` (`full` or `basic`).
- GithubRepoAuditor, MCPAudit, and JobCommandCenter also carry explicit `criticality: high`.

**Pipeline wiring:**
- `portfolio_truth_reconcile.py` computes `risk_entry` after path derivation and wires `RiskFields` into `PortfolioTruthProject`. `doctor_standard` flows through `declared_values` via `_select_declared()`.
- `portfolio_truth_validate.py` validates `risk_tier` against `VALID_RISK_TIERS` and `doctor_standard` against `VALID_DOCTOR_STANDARDS`.
- `portfolio_truth_render.py` adds a `| Risk |` column to the portfolio truth table and a risk posture line to the Coverage Summary.

**Weekly integration:**
- `weekly_command_center.py` counts risk tiers in `_build_truth_summary()`, surfaces `_build_risk_attention_items()` for elevated repos, and adds `risk_posture` to the digest and `## Risk Posture` to the markdown.

**Documentation:**
- `docs/doctor-release-standard.md` documents the full and basic standard with stack-specific patterns.
- `docs/architecture.md` updated with Portfolio Risk Overlay and Cross-Repo Doctor Standard sections, and full directory map with 13 new module entries.

## Cleanup Review

- No debug code added. No stale imports.
- `ruff check src/ tests/` passes clean.
- No backward-compat shims needed — schema bump is purely additive (new fields, no renames/removals).
- `portfolio-catalog.yaml` changes are additive only — no existing field removals.

## Verification Summary

- `python3 -m pytest -q tests/test_portfolio_risk.py` — 11/11 pass
- `python3 -m pytest -q tests/test_portfolio_truth.py` — 13/13 pass (schema 0.4.0, risk field present)
- `python3 -m pytest -q tests/test_portfolio_catalog.py` — 6/6 pass (doctor_standard normalization)
- `python3 -m pytest -q tests/test_weekly_command_center.py` — 1/1 pass (risk_posture in digest and markdown)
- `python3 -m pytest -q` — full suite passing, ruff clean

## Shipped Summary

The portfolio truth snapshot now carries a structured risk overlay on every project. Strategic repos have a declared doctor standard. The weekly command center digest surfaces elevated risk items and a risk posture summary. Schema version is 0.4.0. The 103-108 arc is complete.

## Next Phase

The 103-108 arc is complete. The next arc candidates are:

**Arc A: Context Quality Recovery** — 53 active/recent repos still have weak context. `portfolio_context_recovery.py` was built in Phase 104. A focused arc would systematically run recovery against the worst cohort, targeting real repos and improving the 53 weak-context cases.

**Arc B: Enrichment Layer Risk Integration** — Risk data currently lives in the truth JSON and weekly digest. Wire `risk` through `report_enrichment.py` into workbook Excel, HTML dashboard, and review-pack views so risk posture is visible across all five surfaces, not just two.

**Arc C: Desktop Portfolio Shell** — JobCommandCenter has the Tauri 2 framing. A richer command-center UI that consumes portfolio truth JSON and surfaces risk, path attention, and weekly digest natively.

**Arc D: Safe Automation Expansion** — `decision_quality_v1` provides trust gates and the weekly digest is report-only. A future arc could enable bounded automation (e.g., auto-PR context improvements) for repos with high path confidence and high decision quality, using `doctor_standard` conformance as a prerequisite.

**Arc E: Renderer Simplification** — Five parallel render surfaces (workbook Excel, markdown, HTML dashboard, review-pack, handoff) create a parity tax. Simplifying could reduce maintenance burden.

## Remaining Roadmap

The 103-108 arc is now complete. Future arc candidates are documented above and in the roadmap file.
