# Public Fixture Demo Summary

Status: fixture proof package with public-safe visual capture.

This package establishes the safe public data path for the Operator OS /
Portfolio Command Center demo:

- fixture input: `fixtures/demo/sample-report.json`;
- generated artifacts: `output/demo/`, including the PortfolioCommandCenter
  schema `0.7.0` `projects` payload, weekly digest, burndown, trend snapshots,
  and empty proposal queue;
- desktop consumer: `PortfolioCommandCenter` pointed at `output/demo`;
- private services required: none;
- live writes performed: none.

Captured public-safe frames:

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
