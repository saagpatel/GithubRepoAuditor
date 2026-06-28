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
pnpm demo:desktop:fixture
```

The fixture launch script preloads the public-safe fixture output directory in
the app header.

Use `pnpm demo:desktop` only for manual live or custom-output review. Do not use
the live local default output directory for public recording.

## Captured Frames

Public-safe frames are included under `screenshots/`:

- `00-ops-tauri-window.png` - desktop shell proof.
- `01-portfolio.png` - portfolio table.
- `02-risk-security.png` - risk and security posture.
- `03-burndown.png` - grouped remediation view.
- `04-trends.png` - history and security drift.
- `05-weekly-digest.png` - weekly digest and next move.

The frames show only fixture repos (`RepoA`, `RepoB`, `RepoC`), synthetic
packages, synthetic advisory ids, relative fixture paths, and the fixture output
directory.

## Safety Claim

This package proves the demo can be produced from fixture data. It does not
prove that a recording is visually redacted. A final public recording still
needs a human pass for frame-level privacy review.

## What Stays Private

Do not publish live local portfolio output, real repo names, local absolute
paths, security findings from the real portfolio, terminals, account menus,
Notion, email, calendar, Slack, bridge-db, personal-ops, SecondBrain, tokens,
cookies, env values, or raw agent/session state. The public asset is the pattern:
fixture-backed truth, visible risk, grouped remediation, trend evidence, and one
operator-approved next move.
