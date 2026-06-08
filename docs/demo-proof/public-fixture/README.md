# Public Fixture Demo Proof

This proof package covers the public-safe Portfolio Command Center demo path.

Unlike the private local proof package in `../2026-06-07/`, this package is
designed for external sharing. It uses committed fixture data and generated demo
artifacts under `output/demo/`, so it does not require private repo state,
tokens, Notion, bridge-db, personal-ops, SecondBrain, or notification-hub.

## Generate The Evidence

From the GitHub Repo Auditor repo:

```sh
make demo
python scripts/validate_proof_package.py docs/demo-proof/public-fixture/proof-package.json
```

Expected generated artifacts:

- `output/demo/demo-report.json`
- `output/demo/demo-workbook.xlsx`
- `output/demo/dashboard-sample-user-2026-04-12.html`
- `output/demo/operator-control-center-demo.json`
- `output/demo/operator-control-center-demo.md`
- `output/demo/portfolio-truth-latest.json`
- `output/demo/weekly-command-center-sample-user-2026-04-12.json`
- `output/demo/security-burndown-sample-user-2026-04-12.json`
- `output/demo/pending-proposals.json`
- `output/demo/portfolio-warehouse.db`

## Desktop Demo

From the sibling Portfolio Command Center repo:

```sh
pnpm install
pnpm demo:desktop
```

Then set the output directory in the app header to:

```text
../GithubRepoAuditor/output/demo
```

## Safety Claim

This package proves the demo can be produced from fixture data. It does not
prove that a recording is visually redacted. A final public recording still
needs a human pass for frame-level privacy review.
