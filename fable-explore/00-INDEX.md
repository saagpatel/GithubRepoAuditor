# fable-explore — GHRA discovery, proposals, and public material

*Fable 5 working folder, started 2026-07-10. Mission: (1) understand GHRA deeply and
propose improvements; (2) mine it for public material for saagarpatel.dev.*

## Ground rules in force
- Public-safe = architecture, reasoning, curated public signals only. Never the raw estate.
- Portfolio-health / observability / repo-truth side only. No security-posture work.
- Code changes are drafts/proposals; nothing pushed.

## Index

| Doc | What it is | Status |
|---|---|---|
| [01-how-ghra-thinks.md](01-how-ghra-thinks.md) | The verdict cascade (activity → context → path confidence → attention lane → risk tier), design signatures, tensions T1-T7 | Done |
| [02-audit-layer-scoring.md](02-audit-layer-scoring.md) | Layer 1: 13 analyzers, weights, grades/tiers, 6 verified oddities incl. the dead-weights fiction | Done |
| [03-snapshot-history-and-evolution.md](03-snapshot-history-and-evolution.md) | Live snapshot aggregates (174 projects), history inventory (corrected: scores trend, verdicts don't), provenance quartet #169-#172 | Done |
| [04-field-research.md](04-field-research.md) | Fleet-health viz landscape, dashboard insight principles, explorable-explanations mechanics + Hinsen source-visibility critique | Done |
| [05-improvement-proposals.md](05-improvement-proposals.md) | P1-P9 ranked proposals + explicit non-goals | Done (draft for review) |
| [06-public-material-slate.md](06-public-material-slate.md) | B1-B4 build slate with coverage map vs existing essays | Done (draft for review) |
| [verdict-machine/](verdict-machine/) | **B1 BUILT.** `dist/verdict-machine.html` = the self-contained explainer. `verdict_core.js` = the JS port. `golden/` = the proof (21,254 cases, 100% match). `build_single.mjs` rebuilds dist. | Built + verified |
| [07-essay-who-audits-the-auditor.md](07-essay-who-audits-the-auditor.md) | **B2 PUBLISHED.** ~1,150-word essay for /writing. Opens on the 32→1 overnight collapse; four failures/four receipts (rollups-at-source, producer evidence, lineage, exclusions); seam linter; trust-chain limits. Reviewed against corpus rubrics (Dim 3: Survives), stop-slop clean, zero em dashes. | [Published](https://saagarpatel.dev/writing/who-audits-the-auditor) |
| [08-note-anatomy-of-a-health-verdict.md](08-note-anatomy-of-a-health-verdict.md) | **B4 PUBLISHED.** ~1,300-word note for /notes: the seven-stage teardown with the why behind each rule, honest blind-spot admissions (uncommitted work, universal thresholds, manual-only at ~half), "why there's no score" argument. Links the Verdict Machine + essay 07. | [Published](https://saagarpatel.dev/notes/anatomy-of-a-health-verdict) |
| [diagrams/truth-pipeline.svg](diagrams/truth-pipeline.svg) | **B4 diagram.** Self-contained light/dark SVG: 5 sources → precedence → 6-stage cascade → truth artifact (rollups + producer evidence + exclusions) → 4 consumers, seam linter wrapped around. Verified rendered both modes. | Built + verified |
| [09-essay-permission-to-ignore.md](09-essay-permission-to-ignore.md) | **B3 PUBLISHED.** ~1,150-word essay for /writing: two-of-174 opener, wall-of-amber failure mode, three mechanisms of ignoring (deferred tier, lane vocabulary, capped queue + anti-busywork clause), steelman answered by deferral-downstream-of-declaration, trust condition pointing to 07. Zero em dashes, rubric-reviewed. | [Published](https://saagarpatel.dev/writing/permission-to-ignore) |

## Status: APPROVED BY OPERATOR 2026-07-11, handed off for execution. All public artifacts are FINAL COPY. Remaining work order lives in [10-HANDOFF.md](10-HANDOFF.md) — publish flow, branch merge, P1/P8 implementation, housekeeping. Scoring-hygiene bundle (P7 + mechanical P9) committed on `refactor/scoring-hygiene` at 327e21f, awaiting operator push + merge.

### Publish-order dependencies (when the time comes)
07 (Who Audits the Auditor?) → before/with 08 (anatomy note) and 09 (permission to ignore), both of which link it.
08's "wall of amber" line should link to 09 once live. B1 explainer is standalone; 08 links it.

### Cross-artifact coherence note
Stage numbering is aligned across all three artifacts to the real compute order
(reconcile.py: risk BEFORE attention): explainer Stage 5 = risk, Stage 6 = attention;
note Stage 6 = risk, Stage 7 = ladder (note has the extra "vocabulary move" stage);
diagram boxes 5 = risk, 6 = attention.

### B1 verification receipts (2026-07-11)
- Golden harness: 21,254 Python-generated cases replayed through the JS port, 0 mismatches
  (`cd fable-explore/verdict-machine/golden && node run_golden.cjs`).
- All 5 presets verified via node against `runCascade`: ghost→parked/deferred,
  thin-docs→decision-needed/elevated (toxic pair + no-run-instructions),
  workhorse→active-infra/baseline, archive→archived/deferred,
  CVE→decision-needed/elevated (force-elevate, confidence still high).
- Rendered + eyeballed: dark full-page, light mode, 620px narrow. No overflow, chips fire,
  source views show the live functions via fn.toString().
- Found while porting: `build_risk_entry`'s `path_confidence` parameter is dead in the
  Python body (accepted, never read) — added to P9 hygiene bundle. RESOLVED 2026-07-11:
  param removed on `refactor/scoring-hygiene` (commit 327e21f, with P7 + P9 mechanical
  items); port + golden generator synced, all 21,254 goldens re-pass, dist rebuilt.

## Headline findings (one line each)
- The system's personality: it doubts *itself* before it doubts your repos (path_confidence gates guidance, not judgment).
- Permission to ignore is a first-class output (deferred tier, capped decision queue, "do not refresh docs" clause).
- The provenance quartet (#169-#172) turned the nightly publish into a provenance-checked pipeline — the auditor audits itself.
- Scores trend, verdicts don't (P1). Manual-only holds 52% of the estate (T6).
- The audit layer carries a dead-weights fiction (P7) and partial runs can outscore complete ones (P8) — both cheap, high-honesty fixes.
- Explainer research says: show the machine's source or be self-refuting (Hinsen) — adopted as a hard requirement for B1.
