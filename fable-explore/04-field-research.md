# Field Research: Fleet Health Viz, Dashboard Insight, Interactive Explainers

*Web scout report, 2026-07-10. Distilled; URLs inline.*

## 1. How the industry visualizes fleet health

- **Backstage Soundcheck** (Spotify, paid): tracks (long-term initiatives) → checks
  (pass/fail rules) → facts (raw data points). Three render levels: entity page, group
  grid (red/green scan), org-wide tech-health rollup by team.
  https://backstage.spotify.com/partners/spotify/plugin/soundcheck/
- **Cortex / OpsLevel / Roadie**: dominant pattern is the **ordinal tier rollup**
  (Bronze/Silver/Gold) compressing N services x M checks into one glanceable rank with
  drill-down. OpsLevel splits an org-wide Rubric (drives maturity level) from team
  Scorecards (local, don't affect the global score). Sharpest practitioner critique: **one
  baseline applied to every service regardless of maturity/criticality becomes noise** —
  scope rules per tier. https://docs.opslevel.com/docs/scorecards
- **CHAOSS** (Linux Foundation): explicit philosophy that *not all metrics apply to every
  project* — pick a contextual subset, never a universal scorecard. https://chaoss.community/
- **GitHub community standards**: the humblest pattern — a binary presence checklist with
  a per-gap CTA. No score at all; just a legible gap list.

**Read-across to GHRA:** GHRA independently converged on the industry endgame — scoped
expectations (doctor_standard only for strategic repos, criticality-gated factors), gap
lists over scalar scores, rollups with drill-down. The one industry critique that still
lands is the universal 14/30-day baseline (= proposal P3, cadence-aware staleness).

## 2. Dashboard insight vs noise — principles that survived distillation

- **Stephen Few**: a number without context (threshold/trend/baseline) is noise; kill
  non-data pixels; a dashboard is one holistic display, not a pile of widgets.
- **RED vs USE** (Wilkie/Gregg): choose the metric triad by *whose question you answer* —
  "is this repo healthy for a contributor" vs "is this repo structurally sound" are
  different dashboards over the same data.
- **Honeycomb, "Dashboards or Launchpads"**: dashboards fail when built for glancing but
  used for investigating. Two modes, two artifacts. For a *bounded known question space*
  (which repos need attention), dashboards are the correct tool, not a compromise.
  https://www.honeycomb.io/blog/dashboards-or-launchpads
- **"Dashboards are dead" cycle** resolves the same way every time: not dead, overloaded.
  Right-size the job. https://hex.tech/blog/dashboards-dead/

## 3. Interactive explainers — mechanics that work

Canon: Bret Victor's reactive documents (Tangle.js — sliders *inside the prose*, verdict
rewrites in the sentence), Nicky Case (one simple rule → legible emergent behavior),
Ciechanowski (build up from one naive signal, add complexity stepwise), Red Blob Games
(learn by playing), distill.pub (explanation as research responsibility).

**The 2025-2026 development that matters most for us:** Konrad Hinsen's "Explorable
Explorable Explanations" (Nov 2025) — critique of the whole Victor lineage: the sim behind
the slider is opaque JS you must *trust*. His fix: make the explanation's machinery
drillable to source. https://blog.khinsen.net/posts/2025/11/12/explorable-explorable-explanations.html

For a tool whose entire brand is "nothing gets to self-report," an explainer whose scoring
is a black box would be self-refuting. **The Verdict Machine must show its own source.**

## Design decisions adopted for B1 (The Verdict Machine)

1. **Reactive-document sentence** — verdict rewrites inline in prose as you scrub, Tangle
   style, not a separate results panel.
2. **Ciechanowski build-up structure** — start with commit-age alone, show why it's naive
   (the ghost repo passes), then add context contract, declared intent, confidence gating,
   risk factors, one stage at a time.
3. **Source-visible scoring** (Hinsen) — the actual ported decision functions displayed
   beside the levers; the lit-up code path highlights as signals change. Port must be
   golden-tested against the Python so "this is the real logic" is a true claim.
4. **Threshold-crossing legibility** (Case) — toggles/scrubbers make lane flips land as
   *rules crossed*, never mystery-score drift.
5. **Two modes, honestly split** (Honeycomb) — the explainer is the *investigate* artifact
   for one synthetic repo; a compact fleet-glance strip (anonymized/synthetic tiles) can
   demo the rollup view without touching the estate.
