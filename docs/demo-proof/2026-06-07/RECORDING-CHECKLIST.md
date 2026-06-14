# Portfolio OS 90-Second Recording Checklist

Use this as the operator checklist for recording the 2026-06-07
PortfolioCommandCenter demo. It assumes the proof package in this directory and
the script in `../../../DEMO-SCRIPT.md`.

The numbers below are historical proof values for this captured local package.
For a new live recording, regenerate the proof package and query the current
canonical artifacts before writing spoken lines:

```sh
jq '
def security_sum($field): ([.projects[] | (.security[$field] // 0)] | add) // 0;
{
  generated_at,
  total:(.projects|length),
  attention_counts:.source_summary.attention_state_counts,
  security:{
    scanned:([.projects[] | select(.security.alerts_available == true)] | length),
    with_open_high_critical:([.projects[] | select(((.security.dependabot_critical // 0) + (.security.dependabot_high // 0) + (.security.code_scanning_critical // 0) + (.security.code_scanning_high // 0) + (.security.secret_scanning_open // 0)) > 0)] | length),
    dependabot_critical:security_sum("dependabot_critical"),
    dependabot_high:security_sum("dependabot_high"),
    code_scanning_critical:security_sum("code_scanning_critical"),
    code_scanning_high:security_sum("code_scanning_high"),
    secret_scanning_open:security_sum("secret_scanning_open")
  },
  tool_provenance:([.projects[].declared.tool_provenance // "unknown"] | group_by(.) | map({key:.[0], count:length}))
}' output/portfolio-truth-latest.json

latest_weekly=$(ls -t output/weekly-command-center-*.json | head -n 1)
jq '{generated_at,decision}' "$latest_weekly"
```

## Preflight

- [ ] Run from `/Users/d/Projects/PortfolioCommandCenter`:
  ```sh
  pnpm demo:desktop
  ```
- [ ] Confirm the window title is `Portfolio Command Center Demo`.
- [ ] Confirm the header says `schema 0.5.0`, `129 projects`, and `2026-06-07`.
- [ ] Confirm the output directory field points at the auditor output directory.
- [ ] Set the capture window to a clean 16:9 frame and hide desktop clutter.
- [ ] Keep real repo names blurred, cropped, or moving too quickly to inspect in
  any public cut.

## Shot Order

| Time | Tab | What to Show | Spoken Line |
|---|---|---|---|
| `0:00-0:10` | Portfolio | Open on the full table. Let `Showing 129 of 129 projects` and the risk/security columns breathe. | "This is every repo I've ever started -- a hundred and twenty-nine of them -- in one graded view. Not a commit log. A judgment call on every single one." |
| `0:10-0:28` | Portfolio | Move across risk, context, status, tool, and security columns. Do not linger on individual repo names. | "Each repo carries a risk tier, a context-quality grade, and which agent built it. `git log` gives you a timestamp. This tells you what that timestamp actually means." |
| `0:28-0:48` | Risk + Security | Scroll or frame the security posture block: `117` scanned, `63` open high/critical, `65` critical, `191` high. | "And here's the number a timestamp can never give you -- sixty-three of these repos have a live, high-or-critical security alert. Right now." |
| `0:48-1:02` | Burndown | Show advisory groups and affected repo counts. | "It's not just a count -- it's a fix list. Every advisory is grouped by the one dependency bump that clears it across every repo it touches." |
| `1:02-1:14` | Trends, then Weekly Digest | Flash the charts, then cut to the digest decision ending with `Start with codexkit`. | "It keeps history, so I can watch risk drift over time. And every week it hands me one headline, one decision, one next move." |
| `1:14-1:26` | Header action | Click `Run auditor`; show the app visibly reloading. | "This isn't a static export. I regenerate the truth live, right from the app." |
| `1:26-1:30` | Portfolio | Return to the tool column and hold on Claude Code / Codex attribution. | "And it knows which agent built what -- because two of them work this portfolio, under one control plane." |

## Must-Land Numbers

- `129` total projects.
- `63` repos with open high/critical Dependabot alerts.
- `117` security-scanned repos.
- `65` total open critical alerts.
- `191` total open high alerts.
- Claude Code `53` and Codex `22` tool-provenance counts.
- Weekly Digest decision: `Start with codexkit.`

## Last Pass Before Publish

- [ ] Core cut is 90 seconds or less.
- [ ] The word "sixty-three" is spoken and visible on screen.
- [ ] No terminal scrollback, tokens, hostnames, or absolute home paths appear.
- [ ] Repo names are blurred/cropped if the cut is public.
- [ ] The final frame reinforces Claude Code + Codex under one control plane.
- [ ] Stop the local demo after recording; port `1421` should not remain open.
