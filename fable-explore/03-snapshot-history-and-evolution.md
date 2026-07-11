# Truth Snapshots, History, and the Provenance Quartet

*History scout report, 2026-07-10/11. Aggregates only — no estate details here.*

## The live truth artifact (`output/portfolio-truth-latest.json`)
- generated_at 2026-07-11T04:57Z, schema 0.8.0, plus `derivation_policy_version` and a
  `producer{}` evidence block (see #170 below).
- Top level: schema/generated_at/policy versions, producer, inputs, coverage, exclusions,
  workspace_root, source_summary, precedence_matrix, warnings, projects, rollups.
- **174 projects.** Attention: manual-only 90, archived 33, active-infra 20, experiment 19,
  parked 7, active-product 3, decision-needed 2. Context quality: minimum-viable 85,
  standard 41, boilerplate 30, full 11, none 7. Risk: baseline 121, deferred 37,
  elevated 11, moderate 5. Registry: active 99, recent 35, archived 33, parked 7.
- Per-project record = 8 nested objects (identity 11 fields, declared 15, derived 23,
  risk 7, security 9, advisory 7, provenance 34(!), warnings).
- `exclusions` block live: 1 backup-container dropped under `workspace_discovery.v1`.

**Reading:** decision-needed is nearly drained (2) — the Arc A recovery worked. The estate's
center of mass is manual-only (52%) + minimum-viable context (49%): governable, thinly
described, quiet. Provenance (34 fields) is the largest per-repo block — the receipts
outweigh any single judgment. That's the system's personality in one statistic.

## History — corrected premise
- `output/history/`: 14 audit-report snapshots + `index.json`, 2026-03-25 → 2026-07-04,
  roughly weekly, 0.76 → 7.6 MB as repos_audited grew 115 → 171.
- `index.json` is a compact trend ledger: per-snapshot repos_audited, average_score,
  maturity tier_distribution (shipped/functional/wip/skeleton).
- **History IS read**: `src/history.py` (`load_repo_score_history`, `load_trend_data`) →
  `briefing.py:231`, Excel PortfolioHistory sheet + per-repo sparklines
  (`excel_export.py:542`, `excel_profile_trend_helpers.py`), campaign-outcome trends.

**Surviving gap (P1, revised):** trend machinery covers the *audit layer* (numeric scores,
maturity tiers). The *truth layer* — attention lanes, risk tiers, context quality,
path confidence — has no transition tracking. Truth snapshots (`portfolio-truth-*.json`)
accumulate (the lineage resolver walks them), but nothing answers "which repos changed
lanes since last week and why." Movement exists for scores, not for verdicts.

## The provenance quartet (#169-#172) — hardening scheduled truth
Connective tissue: the nightly publish became a provenance-checked pipeline.

- **#169 producer preflight** (`src/producer_preflight.py`): 4 git checks (origin identity,
  clean worktree, expected ref available, HEAD==expected SHA) → signed `ProducerEvidence`;
  strict schema (40-char SHA, tz-aware timestamps, worktree_clean must be True).
- **#170 require evidence for scheduled truth**: env-gated (`GHRA_REQUIRE_PRODUCER_EVIDENCE`);
  publish hard-fails without evidence; `verify_evidence_still_current` re-runs
  `git rev-parse HEAD` **before and after the write** — catches mid-publish mutation races.
  Evidence embeds in the snapshot as the `producer{}` block.
- **#171 exclusion integrity**: workspace discovery classifies skips with stable reasons
  (backup-container, operator-excluded, generated-evidence, temporary-checkout) and
  publishes `exclusions{policy_version, counts}` — excluded AND auditable, never silent.
- **#172 carried Notion origin** (`src/portfolio_truth_lineage.py`): when Notion is
  unreachable, context carries forward — the resolver now walks predecessor artifacts
  (cycle-safe) to the oldest *real* observation, so carried data can't stamp itself fresh.

One sentence: **prove who produced it, don't count backups as projects, don't lie about
how old carried data is.** This is the "who audits the auditor" essay's evidence base.

## docs/plans
A shipped-work ledger, not a roadmap: attention-state reconciliation (verified 2026-06-19)
and Notion projection policy v2 (shadow-row dedup) both closed. Two deferred operator
decisions noted: archiving one repo; promoting personal-ops to a first-class truth row
(it lives outside the workspace root).
