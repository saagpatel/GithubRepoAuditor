# Public Fixture Recording Checklist

Use this checklist for a public-safe Portfolio Command Center recording.

## Preflight

- [ ] Run `make demo` from `GithubRepoAuditor`.
- [ ] Run `pnpm demo:desktop:fixture` from `PortfolioCommandCenter`. Use this
      target specifically: it sets `VITE_DEMO_OUTPUT_DIR`, which is one of the
      two gates that enable demo redaction.
- [ ] Confirm Portfolio Command Center is pointed at the fixture output directory.
- [ ] Confirm the visible data is fixture data, not the private live portfolio.
- [ ] Confirm the boundary panel reads `demo-org/demo-producer` and shows the
      `FIXTURE / DEMO DATA` pill. If it shows the real producer, demo redaction
      did not engage; stop and fix the launch rather than cropping the frame.
- [ ] Confirm the header output-directory input reads `demo fixture output (path
      redacted for capture)`.
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

## Existing Public-Safe Frames

Use the included `screenshots/` frames as still-image evidence or as the visual
source for a website case-study block. If recording new video, treat these
frames as the reference for what safe output looks like. All eight tabs are
covered, recaptured 2026-08-02 against the `0.11.0` fixture.

## Driving The Tabs Without A Mouse

The tab bar is a `role="tablist"` of plain buttons with no roving `tabindex`, so
arrow keys do not move between tabs, and macOS System Events `click at` does not
reach the WKWebView content. To automate a capture pass: Tab four times from a
fresh window to land on the second tab, then Space to activate. From there each
Tab-then-Space advances exactly one tab. The active tab will carry a keyboard
focus ring, which is genuine rendered UI and safe to publish.
