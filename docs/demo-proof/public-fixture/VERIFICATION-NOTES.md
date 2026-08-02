# Public Fixture Verification Notes

Date: 2026-06-27

## Fixture Truth

- Fixture input: `fixtures/demo/sample-report.json` (audit-report lane) and
  `src/demo_portfolio.py` (PortfolioCommandCenter lane).
- Generated output directory: `output/demo`.
- Portfolio truth schema: sourced from the producer constant
  `src.portfolio_truth_types.SCHEMA_VERSION`, never restated in the generator.
- Visible project names: closed synthetic codename pool (`Aurora Ledger`,
  `Basalt Relay`, ... `Nocturne Spar`); no real repository is named.
- Visible workspace root: `/demo-workspace`.
- Freshness: `generated_at` is six hours before generation time, inside the
  consumer's 48h fresh band.

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

The regenerated truth artifacts were re-checked for the same boundary: no
absolute local path, operator name, or real repository name appears in
`output/demo/portfolio-truth*.json`, and every advisory remains synthetic
(`demo-crypto-core`, `demo-ui-kit`, `demo-transport`, `GHSA-DEMO-0001` through
`GHSA-DEMO-0003`).

Open item: the screenshots above were captured on 2026-06-27 from the previous
three-project `0.7.0` fixture. They no longer depict the generated artifacts and
must be recaptured by the operator before the package is republished. The stale
fixture date that produced the old stale-data banner is resolved: freshness is
now computed at generation time, and `scripts/validate_proof_package.py` fails
the package if the published truth ever drifts out of the fresh window or off
the producer's current schema.
