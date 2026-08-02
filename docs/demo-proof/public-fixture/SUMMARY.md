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

Captured public-safe frames, recaptured 2026-08-02 against the synthetic
`0.11.0` portfolio described above:

- `screenshots/00-ops-tauri-window.png`: Tauri desktop shell on the Ops tab,
  reading the fixture output directory.
- `screenshots/01-portfolio.png`: Portfolio tab.
- `screenshots/02-risk-security.png`: Risk + Security tab.
- `screenshots/03-burndown.png`: Burndown tab.
- `screenshots/04-trends.png`: Trends tab.
- `screenshots/05-weekly-digest.png`: Weekly Digest tab.
- `screenshots/06-decisions.png`: Decisions tab.
- `screenshots/07-automation.png`: Automation tab.

All eight frames come from the same live Tauri window launched with
`pnpm demo:desktop:fixture`, normalised to 1280x820 and captured at native
2560x1640. Nothing is mocked, cropped, or composited: the producer identity and
output path shown in the frames are redacted by the app itself, in demo mode,
while the underlying boundary checks continue to verify the real producer. See
VERIFICATION-NOTES.md.
