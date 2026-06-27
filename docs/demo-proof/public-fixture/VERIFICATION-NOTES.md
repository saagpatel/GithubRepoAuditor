# Public Fixture Verification Notes

Date: 2026-06-27

## Fixture Truth

- Fixture input: `fixtures/demo/sample-report.json`.
- Generated output directory: `output/demo`.
- Portfolio truth schema: `0.7.0`.
- Visible project names: `RepoA`, `RepoB`, `RepoC`.
- Visible workspace root: `fixtures/demo`.

## Commands Run

```sh
./.venv/bin/python scripts/build_demo_artifacts.py
./.venv/bin/python scripts/validate_proof_package.py docs/demo-proof/public-fixture/proof-package.json
pnpm typecheck
pnpm test
pnpm build
pnpm demo:desktop:fixture
```

## Visual Capture

- Desktop shell frame captured from the live Tauri window with `screencapture -l`.
- Tab frames captured from the PortfolioCommandCenter React app served by Vite,
  with Tauri IPC mocked to the same fixture files in `output/demo`.
- Captured tabs: Portfolio, Risk + Security, Burndown, Trends, Weekly Digest.

## Public-Safety Review

Manual inspection confirmed the retained frames show fixture labels only:

- repo names are `RepoA`, `RepoB`, `RepoC`;
- paths are relative fixture paths such as `fixtures/demo/RepoA`;
- app output directory is the public fixture output directory;
- advisories and packages are synthetic (`demo-runtime`, `demo-ui-kit`,
  `GHSA-DEMO-0001`, `GHSA-DEMO-0002`);
- no terminal, browser chrome, account menu, local absolute path, token, email,
  calendar, Slack, Notion row, bridge-db row, personal-ops data, SecondBrain
  content, or real security finding is visible.

Known visible caveat: the fixture date is intentionally `2026-04-12`, so the app
shows a stale-data banner on 2026-06-27. That banner is public-safe, but a future
polish pass may choose to make fixture freshness deterministic for public demos.
