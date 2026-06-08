# Public Fixture Recording Checklist

Use this checklist for a public-safe Portfolio Command Center recording.

## Preflight

- [ ] Run `make demo` from `GithubRepoAuditor`.
- [ ] Run `pnpm demo:desktop` from `PortfolioCommandCenter`.
- [ ] Point Portfolio Command Center at `GithubRepoAuditor/output/demo`.
- [ ] Confirm the visible data is fixture data, not the private live portfolio.
- [ ] Hide terminals, path bars, desktop clutter, account menus, and notification banners.

## Shot Order

| Time | Tab | What to show |
| --- | --- | --- |
| 0:00-0:10 | Portfolio | The table and portfolio summary. |
| 0:10-0:25 | Portfolio | Risk, status, context, and tool/provenance columns. |
| 0:25-0:42 | Risk + Security | Portfolio-level risk and security posture. |
| 0:42-0:58 | Burndown | Advisory-grouped fix guidance. |
| 0:58-1:12 | Trends | Risk and alert history. |
| 1:12-1:25 | Weekly Digest | One headline, one decision, one next move. |
| 1:25-1:30 | Portfolio | Close on the Operator OS thesis. |

## Do Not Publish If Visible

- private repo names;
- local absolute paths;
- hostnames, usernames, or account menus;
- real security advisory details;
- Notion, email, calendar, Slack, bridge-db, or SecondBrain content;
- terminal scrollback, env vars, tokens, cookies, or config files.
