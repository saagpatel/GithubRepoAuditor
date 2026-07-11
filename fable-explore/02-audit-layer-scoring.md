# Layer 1: The Audit Scoring Map

*Analyzer scout report, 2026-07-10/11. Security analyzer noted fields-only per ground rules.*

## Shape
13 analyzers subclass `BaseAnalyzer` (`src/analyzers/base.py:13`), each emitting an
`AnalyzerResult` score clamped to [0,1]. Composition lives in `src/scorer.py`.

| Analyzer | Score recipe (additive) | scorer.WEIGHTS |
|---|---|---|
| readme | +0.2 exists, +0.2 length, +0.2 sections, +0.2 install/usage, +0.1 badges, +0.1 code (`readme.py:112-162`) | .12 |
| structure | layout/src/tests/config bumps (`structure.py:85-137`) | .10 |
| code_quality | +0.3 lint, +0.2 types, +0.15 hooks, commit hygiene ×0.15 (`code_quality.py:69-127`) | .15 |
| testing | +0.4 tests exist, +0.3 framework, +0.3 coverage (`testing.py:43-62`) | .18 |
| cicd | +0.5 workflow, +0.3 quality steps, +0.2 badge (`cicd.py:48-73`) | .10 |
| dependencies | +0.4 manifest, +0.4 lockfile, +0.2 fresh (`dependencies.py:103-157`) | .08 |
| activity | recency bands +0.3/+0.2/+0.1, +0.2 pattern, +0.1 bus factor, +0.2 releases (`activity.py:39-87`) | .15 |
| documentation | docs/API/changelog/examples (`completeness.py:69-99`) | .02 |
| build_readiness | manifest/make/docker/env (`completeness.py:129-160`) | .07 |
| community_profile | present/10 GitHub health files (`community_profile.py:111`) | .03 |
| interest | 8 raw components, separate axis | 0 |
| security | starts 1.0, deducts; advisory | 0 |
| description | emits `description_confidence` only | (unscored) |

- `overall_score` = weighted average **self-normalized over present dimensions**
  (`scorer.py` `score_repo`). Grades A≥.80/B≥.70/C≥.55/D≥.35/F. Completeness tiers:
  shipped≥.75, functional≥.55, wip≥.35, skeleton≥.15, else abandoned — with overrides:
  fork demotes activity weight, archived caps at functional, pushed_at >730d caps at wip,
  zero meaningful files forces skeleton.
- Scoring profiles (`config/scoring-profiles/`: default, job-search, shipping) fully
  replace the 10 completeness weights; grades/tiers/staleness constants are NOT
  profile-tunable.
- Portfolio: avg score, portfolio grade, "best work" = overall×0.6 + interest×0.4.

## Oddities (scout-verified, my ranking)

1. **The dead-weights fiction.** Every analyzer declares a `.weight` class attribute;
   actual scoring uses a *different* dict (`scorer.WEIGHTS`). They disagree (readme .15 vs
   .12, testing .15 vs .18, documentation .05 vs .02…) and the analyzer attrs sum to 1.03.
   Nothing consumes them. Anyone reading analyzer files to understand scoring reads fiction.
2. **Partial runs can outscore complete ones.** Self-normalizing denominator: absent
   dimensions shrink the basis instead of penalizing. An offline run (GitHub analyzers
   skipped) silently grades on fewer dimensions — an unlabeled basis change in an honesty
   tool. No floor on `weight_sum`, no `scored_basis` disclosure in the report.
3. **`description` looks like a scored dimension but isn't** — feeds only
   `context_quality_score`.
4. **Interest score's ceiling is uncalibrated** vs its tier thresholds (flagship ≥0.70
   assumes ~1.0 ceiling; components can theoretically exceed it).
5. **Magic constants immune to profiles** — STALE_THRESHOLD_DAYS=730, novelty haircut
   at 0.30 language frequency, tier/grade bands: all fixed module constants.
6. **community_profile mildly double-counts** readme/description signals (0.03 weight).
