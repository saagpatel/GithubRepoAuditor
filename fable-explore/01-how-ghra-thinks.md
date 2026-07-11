# How GHRA Thinks: The Verdict Cascade

*Deep-read of the portfolio-truth layer, 2026-07-10. File:line refs against main @ f58ad43.*

GHRA's core move is a **cascade of small, legible judgments** that compound into a verdict.
Nothing is a black-box score; every verdict is a chain of if-statements you can read in one
sitting. That's the design signature: auditability of the auditor.

## The cascade, one repo at a time

### 1. Is it alive? — `activity_status`
`src/portfolio_truth_sources.py:330` + `src/portfolio_truth_reconcile.py:960`

- Evidence = git `last_commit_at`, falling back to newest mtime of *meaningful* files
  (source extensions + allowlisted text/manifests; vendor dirs, dotfiles, symlinks excluded —
  `_latest_meaningful_mtime`, sources.py:615).
- Thresholds: **≤14d = active, ≤30d = recent, else stale**. GitHub-archived or lifecycle
  archived short-circuits to `archived`.
- Notable: in a git repo, *uncommitted work does not count as life* (commit date wins).
  Honest by one reading, blind by another.

### 2. Registry status — `_registry_status_for` (reconcile.py:979)
Trivial mapping: stale → `parked`, otherwise passthrough. Staleness is immediately
re-framed as an *attention* word, not a *judgment* word.

### 3. Does it explain itself? — `context_quality`
`src/portfolio_context_contract.py:137` (`analyze_project_context`)

Categorical contract with 6 required sections (aliases allowed): **What-This-Is,
Current-State, Stack, How-To-Run, Known-Risks, Next-Move**. Checked in the primary context
file (AGENTS.md preferred) with a README fallback, plus a lead-paragraph fallback for the
summary (real-world convention honored, not fought).

- No primary file and no README → `none`
- Any required section missing → `boilerplate`
- All present → `minimum-viable`; supporting files upgrade to `standard` / `full`

**Key property: this is presence-based, not truth-based.** A Current-State section that
*exists but lies* passes. (The audit layer has readme-staleness signals, but the categorical
contract doesn't consume them.)

### 4. What did the operator say? — declared intent
`PRECEDENCE_MATRIX` (reconcile.py): catalog_repo > catalog_group > catalog_default >
legacy_registry > notion. Declarations (operating_path, disposition, criticality,
doctor_standard) come from `config/portfolio-catalog.yaml`.

### 5. Should we trust the declared path? — `path_confidence`
`src/portfolio_pathing.py:43` (`build_operating_path_entry`)

Concerns accumulate: missing-operating-path, program-disposition-conflict,
missing-explicit-contract, intent-needs-review, **weak-context** (quality ∈
{none, boilerplate}), archived-outside-archive-path, repo-state-below-path-bar.

- Any hard concern → confidence **low** → `path_override = "investigate"`
- No explicit contract, or only minimum-viable context, or shaky decision-quality → **medium**
- Otherwise **high**

This is the system's *epistemics layer*: it doesn't distrust the repo, it distrusts
**its own ability to give guidance** about the repo.

### 6. Where does it sit in my attention? — `attention_state`
`_attention_state_for` (reconcile.py:985). Strict priority ladder:

1. `archived` (github_archived OR registry OR lifecycle OR archive path)
2. `experiment` (path/disposition/lifecycle says so)
3. `parked` (registry parked)
4. `decision-needed` — investigate override, OR **no operating path**, OR **security_risk**
5. `active-infra` / `active-product` — active+maintained AND categorized infra/commercial
6. `manual-only` — the default bucket for everything else active
7. `parked` — the fallthrough

So **decision-needed ≈ "I can't trust my own guidance here"** — mostly a thin-docs lane
(verified previously: it's keyed to context quality, not intent).

### 7. How risky is neglect? — `risk_tier`
`src/portfolio_risk.py:53` (`build_risk_entry`)

- Short-circuit **deferred**: archived/archive-path, or stale-and-not-maintain.
  ("You're allowed to ignore this" is an explicit output.)
- 7 factors: weak-context-active, investigate-override, missing-operating-path,
  missing-doctor-standard (strategic repos only), no-run-instructions,
  undocumented-risks (high-criticality only), active-high-severity-alerts.
- **elevated** = 3+ factors, OR (weak-context-active AND investigate-override), OR an open
  critical CVE on an active repo (force-elevate — a lone critical can't hide).
- 1-2 factors = moderate, 0 = baseline.

### 8. Portfolio rollups — computed once, at the source
`PortfolioTruthRollups.from_projects` (portfolio_truth_types.py:226). The docstring names
the reason: downstream consumers re-deriving risk logic was "the #1 drift risk." The
producer ships the aggregates so consumers can't drift.

### 9. The decision queue — capped, evidence-stamped
`src/portfolio_decision_queue.py:54`. Only security follow-ups and decision-needed repos
qualify; every item carries evidence, source freshness, and a standing instruction:
*"Do not refresh context, roadmap, handoff, AGENTS, or docs unless that work directly
resolves this decision."* Anti-busywork encoded as data.

### 10. The seam linter — the auditor audits itself
`src/operator_os_seam_linter.py` (`lint_operator_os_seams`). Checks artifact freshness
(staleness hours), contract shadowing, catalog/declaration parity, rollup integrity,
carried-value freshness, exclusion integrity, schema pins, and **identity resolution across
the other systems' databases** (bridge-db, notification-hub, Notion snapshot). This exists
because the truth file goes stale and identities drift — both bit us before.

## Design signatures worth naming

1. **Declared vs observed, reconciled with receipts.** Every field knows its source; the
   precedence matrix is explicit; rationale strings are built alongside verdicts.
2. **Confidence gates guidance, not judgment.** The system never says "bad repo" — it says
   "I can't advise you here yet" (investigate) and routes attention.
3. **Deferral is a first-class verdict.** `deferred` risk and the parked lane are permission
   to ignore, which is what keeps 130+ repos governable.
4. **Drift is treated as the main enemy** — rollups at source, seam linter, producer
   evidence requirements (recent PRs #169/#170), schema pinning.

## Tensions / blind spots (candidate proposals live in 05)

- **T1 — Two context-quality systems.** Categorical contract (truth layer) vs numeric
  composite `context_quality_score` (audit layer, `src/context_quality.py`: 30% description
  confidence + 25% readme freshness + 25% catalog completeness + 20% completeness). Different
  inputs, different layers, can disagree. Which one is "the" context quality?
- **T2 — Presence ≠ truth.** The contract checks that Current-State *exists*, not that it
  matches observed reality. The site already has status-claims gates; GHRA itself doesn't
  cross-examine a repo's self-description against its signals.
- **T3 — No cadence model.** 14/30-day thresholds are universal. A quarterly-cadence tool is
  "stale" 90% of its life; a repo you touch daily that goes quiet for 3 weeks looks the same
  as one that's naturally slow. No notion of *expected* cadence or "overdue vs resting."
- **T4 — Verdicts have no memory (corrected).** The audit layer DOES trend (score
  sparklines, PortfolioHistory sheet via `src/history.py`). But the truth layer doesn't:
  no lane-transition ledger, no risk-tier movement, no context-quality deltas across the
  accumulated `portfolio-truth-*.json` artifacts. Scores trend; verdicts don't.
- **T5 — Uncommitted work is invisible** when a repo has any commit history (commit date
  short-circuits the mtime fallback, sources.py:330).
- **T6 — `manual-only` is a catch-all — and it's the majority.** Live snapshot: 90 of 174
  projects (52%) sit in manual-only. Fine as a lane, weak as a signal when it's the mode
  of the whole distribution.
- **T7 — Crisp lanes, no borderline visibility.** A repo at 13 days vs 15 days of quiet is
  active vs recent; nothing surfaces "about to change lanes."
