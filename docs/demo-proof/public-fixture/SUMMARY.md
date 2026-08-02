# Public Fixture Demo Summary

Status: fixture proof package with public-safe visual capture.

This package establishes the safe public data path for the Operator OS /
Portfolio Command Center demo:

- fixture input: `fixtures/demo/sample-report.json` for the audit-report lane,
  and the closed-pool synthetic portfolio in `src/demo_portfolio.py` for the
  PortfolioCommandCenter lane;
- generated artifacts: `output/demo/`, including a 40-project PortfolioCommandCenter
  `projects` payload at the producer's current truth schema with receipt-backed
  security coverage, nine timestamped trend snapshots, weekly digest, burndown,
  and a mixed-state proposal queue;
- fixture freshness: the truth snapshot is stamped six hours before generation,
  so the app renders it as fresh rather than showing a stale-data banner;
- desktop consumer: `PortfolioCommandCenter` pointed at `output/demo`;
- private services required: none;
- live writes performed: none.

Captured public-safe frames (captured from the previous three-project `0.7.0`
fixture; they predate the synthetic portfolio above and need recapture before
republication):

- `screenshots/00-ops-tauri-window.png`: Tauri desktop shell reading the fixture
  output directory.
- `screenshots/01-portfolio.png`: Portfolio tab.
- `screenshots/02-risk-security.png`: Risk + Security tab.
- `screenshots/03-burndown.png`: Burndown tab.
- `screenshots/04-trends.png`: Trends tab.
- `screenshots/05-weekly-digest.png`: Weekly Digest tab.

The tab frames were captured from the PortfolioCommandCenter React surface with
Tauri IPC mocked to the same fixture files under `output/demo/`. The desktop
shell frame was captured from the live Tauri window launched with the fixture
output path preselected.
