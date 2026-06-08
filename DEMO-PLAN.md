# Portfolio Command Center Demo Plan

This is the public-safe demo plan for the Operator OS wedge.

The demo should prove one thing quickly: a serious builder can turn repo sprawl and agent-touched work into verified truth, visible risk, and one next move.

## Demo Thesis

Git history tells you what changed. Portfolio Command Center tells you what the change means.

## Demo Modes

Use one of two modes:

| Mode | Use for | Data source | Public-safe |
| --- | --- | --- | --- |
| Fixture mode | Public recording, docs, external sharing | `fixtures/demo/sample-report.json` via `make demo` | Yes |
| Live local mode | Private operator proof and internal review | `output/portfolio-truth-latest.json` from the real local portfolio | No, unless redacted |

Default to fixture mode for anything public.

## Fixture Demo Setup

From this repo:

```sh
make demo
```

Expected outputs:

- `output/demo/demo-report.json`
- `output/demo/demo-workbook.xlsx`
- `output/demo/dashboard-*.html`
- `output/demo/operator-control-center-demo.json`
- `output/demo/operator-control-center-demo.md`
- `output/demo/portfolio-truth-latest.json`
- `output/demo/portfolio-warehouse.db`

Then launch the desktop shell from the sibling app:

```sh
cd ../PortfolioCommandCenter
pnpm install
pnpm demo:desktop
```

In the app header, set the output directory to:

```text
../GithubRepoAuditor/output/demo
```

If the recording needs live-shaped data, create a sanitized output directory first. Do not point a public recording at the private live `output/` directory.

## 90-Second Arc

| Time | Frame | Spoken line |
| --- | --- | --- |
| 0:00-0:10 | Portfolio table | "This is the problem AI builders are about to have: not one repo, but a portfolio of agent-touched work." |
| 0:10-0:25 | Risk/context/status columns | "A commit timestamp is not enough. I need to know which projects are healthy, blocked, risky, stale, or worth ignoring." |
| 0:25-0:42 | Risk + Security | "The control plane turns raw alerts and project facts into an attention map, so risk stops hiding in individual repos." |
| 0:42-0:58 | Burndown | "The useful question is not just 'what is broken?' It is 'which fix clears the most portfolio pain?'" |
| 0:58-1:12 | Trends | "Because it keeps history, I can tell whether the portfolio is improving or just getting noisier." |
| 1:12-1:25 | Weekly Digest | "Every week, the system reduces the mess to one headline, one decision, and one next move." |
| 1:25-1:30 | Return to Portfolio | "That is Operator OS: verified truth for builders using agents at portfolio scale." |

## Must-Land Product Points

- The app is reading generated artifacts, not a hand-maintained spreadsheet.
- Portfolio truth, weekly digest, burndown, and charts come from the same evidence chain.
- The operator remains in charge.
- Public demo data is fixture-backed or sanitized.
- Private local systems are implementation references, not public data sources.

## Do Not Show Publicly

- Real private repo names.
- Local absolute paths under the user's home directory.
- Real GitHub security alert details.
- Notion database rows or page IDs.
- Gmail, Calendar, Drive, Slack, or task data.
- Codex sessions, memories, hook logs, or SQLite databases.
- SecondBrain raw captures or conversation exports.
- Tokens, cookies, env values, terminal scrollback, hostnames, or account settings.

## Redaction Checklist

Before publishing:

- [ ] Confirm the app is using `output/demo` or another sanitized output directory.
- [ ] Confirm no private repo names are readable.
- [ ] Confirm no terminal panes or local paths are visible.
- [ ] Confirm no account names, tokens, hostnames, or private URLs are visible.
- [ ] Confirm screenshots and video frames do not expose Notion, email, calendar, Slack, or SecondBrain.
- [ ] Confirm any local live proof package is described as private/local evidence only.

## Verification Checklist

Run:

```sh
make demo
python scripts/validate_proof_package.py docs/demo-proof/public-fixture/proof-package.json
```

For the desktop shell:

```sh
cd ../PortfolioCommandCenter
pnpm typecheck
pnpm test
pnpm build
```

Visual verification is complete only after the app is opened against the fixture output and the Portfolio, Risk + Security, Burndown, Trends, and Weekly Digest tabs all render without private data.

## Final Public Framing

Use this closing sentence:

> Operator OS is the missing control plane for AI-assisted builders: it turns scattered agent work and repo sprawl into verified truth, visible risk, and one operator-approved next move.
