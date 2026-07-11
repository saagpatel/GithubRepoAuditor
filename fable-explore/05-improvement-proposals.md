# Improvement Proposals (draft — for operator review, nothing implemented)

*Status: revised after all three scout reports landed (02/03/04). Ranked by how much
honesty-per-effort each buys.*

Each proposal states: the gap, the evidence, the sketch, and the cost. These are drafts to
review, not work I've started.

---

## P1 — Verdict-transition ledger: trend the truth layer, not just the scores
**Gap (T4, premise corrected by scout 03):** history/trends DO exist — for the *audit
layer* (`src/history.py` → score sparklines, PortfolioHistory Excel sheet, maturity-tier
distribution in `history/index.json`). What has no memory is the **truth layer**: nothing
tracks attention-lane transitions, risk-tier changes, context-quality deltas, or
path-confidence movement across the accumulated `portfolio-truth-*.json` artifacts (which
the #172 lineage resolver already proves are walkable).
**Sketch:** a `portfolio_truth_trends.py` that walks the last N truth artifacts and emits,
per repo: lane transitions (with dates), activity-status streaks, risk-tier changes.
Surface: a `## Movement` section in the weekly command center digest ("3 repos slid
active→stale; 1 recovered decision-needed→active-infra") + a transitions block in rollups.
**Why it's honest:** scores trend but *verdicts* don't; a point-in-time lane can't
distinguish resting from decaying. Direction is the missing half of every verdict — and
lane flips are exactly what an overnight regen swings (the 32→1 decision-needed collapse).
**Cost:** medium — pure read-side module + digest section; sibling artifact, no schema change.

## P2 — Claims parity: cross-examine Current-State against evidence
**Gap (T2):** the context contract verifies that a `Current-State` section *exists*, not
that it's plausible. A README claiming "shipped, tests green" with no CI, no tests dir, and
90 days of silence passes `minimum-viable` as easily as an honest one. The website already
has status-claims gates; the auditor itself doesn't cross-examine.
**Sketch:** a narrow, deterministic checker: extract tense/status keywords from
Current-State ("shipped", "in progress", "weekly", "v1.0") and diff against derived facts
(has_tests, has_ci, release_count, activity_status). Mismatch → new pathing concern
`state-claims-unverified` → path_confidence capped at medium. Start report-only.
**Why it's honest:** this is the "Ghost" essay's discipline, mechanized — the README's
claim finally submits to cross-examination inside the tool that inspired the essay.
**Cost:** medium — keyword extraction must stay conservative to avoid false accusations;
report-only first pass makes that safe.

## P3 — Cadence-aware staleness: overdue vs resting
**Gap (T3):** 14/30-day thresholds are universal. A quarterly-maintenance tool spends 90%
of its life "stale"; the deferred short-circuit then hides it from risk entirely unless
it's on maintain. There is no concept of *expected* cadence.
**Sketch:** optional catalog field `expected_cadence: weekly|monthly|quarterly|dormant-ok`.
Activity status stays as-is (it's an observation); what changes is the *interpretation*:
a new derived flag `overdue` (quiet for > 2x expected cadence on maintain/finish paths) and
"stale" stops implying neglect for `dormant-ok` repos. Defaults preserve current behavior.
**Why it's honest:** it moves a hidden universal assumption ("all repos should move
monthly") into a declared, per-repo contract — the system's own declared-vs-observed
pattern applied to time.
**Cost:** low-medium — one catalog field, one derived flag, threshold table.

## P4 — Reconcile the two context-quality systems
**Gap (T1):** categorical `context_quality` (truth layer, section-presence contract) and
numeric `context_quality_score` (audit layer, weighted composite) share a name and
overlapping-but-different inputs, live in different artifacts, and can disagree. Which one
does a consumer trust?
**Sketch:** smallest honest fix is a rename + docs (`context_quality` stays the contract;
score becomes `audit_context_score`), plus a seam-linter check that flags repos where the
two diverge sharply (contract says `standard`+ but composite < 0.4, or inverse) — the
divergence itself is signal: it usually means fresh-looking docs with stale substance or
vice versa.
**Cost:** low. The divergence lint is the interesting part.

## P5 — Dirty-worktree visibility
**Gap (T5):** in any repo with commit history, uncommitted work is invisible — commit date
short-circuits the mtime fallback (`portfolio_truth_sources.py:330`). "Work isn't real
until committed" is a defensible stance, but *silently* discarding the signal isn't: a repo
with 40 modified files and a 60-day-old last commit reads as plain "stale," when it's
actually "stalled mid-change," a different and more urgent state.
**Sketch:** derived boolean `worktree_dirty` (+ count), already computable from the git
facts pass. Does NOT count as activity; surfaces as a decision-queue evidence line and a
pathing rationale note. (Arc A already defers on dirty worktrees for writebacks — the
signal exists at the edges; promote it into truth.)
**Cost:** low.

## P6 — Lane hysteresis / borderline surfacing
**Gap (T7):** lanes flip on crisp day-thresholds. A repo at day 13 vs day 15 is a
different attention state; overnight regen can swing counts (the 32→1 decision-needed
collapse we logged before). Nothing says "about to change lanes."
**Sketch:** emit `lane_margin` (days until the next threshold) in derived fields; weekly
digest gets a two-line "at the edge" list. Optionally require 2 consecutive snapshots to
confirm a transition before rollups count it (true hysteresis) — needs P1's history reads.
**Cost:** low for margin; medium for hysteresis.

## P7 — Kill the dead-weights fiction
**Gap (scout 02, oddity 1):** every analyzer declares a `.weight` class attribute that
nothing consumes; real weights live in `scorer.WEIGHTS`. The two disagree on 5 of 10
dimensions and the dead set sums to 1.03. Anyone (human or agent) reading an analyzer file
to understand scoring is reading fiction — in the codebase whose premise is that
self-descriptions must match reality.
**Sketch:** delete the `.weight` attributes (or make `scorer.WEIGHTS` derive from them —
pick ONE source of truth), plus a regression test asserting weights sum to 1.0 and every
scored dimension has exactly one declared weight.
**Cost:** small. Highest honesty-per-line in this document.

## P8 — Disclose the scoring basis on partial runs
**Gap (scout 02, oddity 2):** `overall_score` self-normalizes over *present* dimensions.
A run where GitHub-dependent analyzers didn't fire silently grades on a smaller basis —
so a partial audit can outscore a complete one, unlabeled. That's a quiet basis change in
a tool that exists to prevent exactly this class of lie.
**Sketch:** emit `scored_dimensions` / `scored_weight_sum` per repo; below a threshold
(e.g. < 0.85 of full basis) mark the grade qualified ("B on 7/10 dimensions") in JSON,
Excel, and dashboard. Optionally a conservative mode that treats missing dims as 0 for
tier gating. Report-only first.
**Cost:** small-medium — plumbing a disclosure, not changing the math.

## P9 — Scoring hygiene bundle (smaller, grouped)
- **Centralize magic constants** (STALE_THRESHOLD_DAYS=730, tier/grade bands, novelty
  haircut) into the scoring profile so profiles can genuinely re-purpose the audit
  (scout 02, oddity 5).
- **Label `description` as unscored** wherever dimensions render (oddity 3).
- **Calibrate interest ceiling** or clamp component sum so `flagship ≥ 0.70` means what it
  says (oddity 4).
- **De-overlap community_profile** vs readme/description or accept and document the
  double-count (oddity 6).
- **Dead parameter:** `build_risk_entry(path_confidence=...)` is accepted but never read
  in the body (found while porting for the Verdict Machine golden harness). Drop it or
  use it.
**Cost:** each is small; bundle for one hygiene pass.

---

## Non-goals (considered, rejected)
- **A single composite health score (0-100).** The system's strength is legible lanes +
  factor lists. A scalar would be more impressive and less honest — it hides *why*.
- **ML/heuristic liveness prediction.** The audience for this tool is one operator who
  needs receipts, not forecasts without evidence chains.
- **Auto-writeback of any verdict into repos.** Existing approval rails are the boundary;
  keep it.
