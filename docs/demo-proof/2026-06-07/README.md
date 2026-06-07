# Portfolio OS Demo Proof - 2026-06-07

Durable screenshot proof for the five-tab local PortfolioCommandCenter demo.

Captured from `/Users/d/Projects/PortfolioCommandCenter` with:

```sh
pnpm demo:desktop
```

The demo command uses `src-tauri/tauri.demo.conf.json`, Vite port `1421`, and
the window title `Portfolio Command Center Demo`.

## Source Truth

- Truth artifact: `output/portfolio-truth-latest.json`
- Truth generated at: `2026-06-07T08:32:03.303071+00:00`
- Schema: `0.5.0`
- Projects: `129`
- Weekly digest: `output/weekly-command-center-saagpatel-2026-06-03.json`

## Proof Points

- Portfolio: `129` projects visible in the header and table count.
- Risk + Security: `117` scanned, `63` repos with open high/critical
  Dependabot alerts, `65` total critical, `191` total high.
- Burndown: advisory-grouped fix list with affected repo counts.
- Trends: risk tier and open high/critical history charts.
- Weekly Digest: current decision ends with `Start with codexkit.`

## Files

- `images/01-portfolio.png`
- `images/02-risk-security.png`
- `images/03-burndown.png`
- `images/04-trends.png`
- `images/05-weekly-digest.png`
- `images/contact-sheet.png`

The contact sheet is the quickest visual smoke check for all five frames.
