# Weekly Review

Use this guide for the normal ongoing operator loop. If you need the broader product map first, start with [modes.md](/Users/d/Projects/GithubRepoAuditor/docs/modes.md). If something is broken, jump to [operator-troubleshooting.md](/Users/d/Projects/GithubRepoAuditor/docs/operator-troubleshooting.md).

## Weekly cadence

1. Run `audit <github-username> --doctor` if setup, baseline, or workbook health is in doubt.
2. Run `audit <github-username> --html` to refresh the workbook, Markdown, HTML, JSON, and weekly-pack story.
3. Run `audit <github-username> --control-center` for read-only operator triage from the latest state.
4. Open the workbook and read it in this order:
   - `Dashboard`
   - `Run Changes`
   - `Review Queue`
   - `Portfolio Explorer`
   - `Repo Detail`
   - `Executive Summary`

## How to read the weekly surfaces

The primary workbook, HTML, Markdown, and review-pack surfaces all tell the same compressed operator story:

- `Act Now` means blocked or urgent pressure is active right now.
- `Watch Closely` means the repo is active and deserves attention, but it does not outrank the highest-pressure work yet.
- `Improving` means the path is stabilizing and recent action is helping.
- `Fragile` means progress is real but easy to lose.
- `Revalidate` means confidence still needs to be rebuilt before the repo should be treated as restored.

Read those buckets in exactly that order. The hidden workbook sheets and raw JSON still keep the richer lifecycle detail underneath.

## Workbook reading order

- `Dashboard` tells you whether the portfolio is quiet, worsening, or moving in the right direction.
- `Run Changes` tells you what moved this run before you jump into action.
- `Review Queue` tells you what deserves time now.
- `Portfolio Explorer` helps compare repos after you know where the pressure is.
- `Repo Detail` is where one-repo decisions happen.
- `Executive Summary` is the short shareable readout once you already understand the weekly story.

## Control-center reading order

When you open the control-center artifact, read it in this order:

1. `Headline`
2. `Trend`
3. `Why it matters`
4. `What to do next`
5. `Primary target`
6. `Queue lanes`

That sequence tells you whether the portfolio is actually changing, why the top target is still the top target, and whether the next move belongs in normal weekly review or in Action Sync.

## What a good weekly review looks like

- Clear `Blocked` work before everything else.
- Treat `Needs Attention Now` as the main weekly closure lane.
- Use `Repo Detail` when one repo needs a real decision instead of a quick pass.
- Leave `Safe to Defer` alone unless your priorities changed.
- Only move into campaigns, writeback, GitHub Projects, or Notion sync when the local workbook and control-center story is already settled.

## When to move into Action Sync

Use the shared `Action Sync Readiness` summary in the workbook, HTML, Markdown, review-pack, or control-center:

- `drift-review` means review managed drift before you sync anything else.
- `blocked` means the campaign has useful local work, but a prerequisite or approval still needs attention.
- `apply-ready` means the local story is settled enough that you can sync outward if you choose.
- `preview-ready` means the campaign is worth previewing next, but the product is still nudging you to stay preview-first.
- `idle` means there is no good reason to leave the local weekly loop yet.

Then use the shared `Apply Packet` handoff to decide the exact next move:

- `review-drift` means stop and review managed drift before you sync anything else.
- `needs-approval` means the campaign is close, but governance approval or rollback review still blocks apply.
- `ready-to-apply` means the local story is settled enough that an explicit apply command is reasonable if you choose it.
- `preview-next` means use the suggested preview command next, then decide whether the campaign is really ready to apply.
- `stay-local` means keep working in the local weekly loop for now.

If the packet shows a command hint:
- preview commands never include `--writeback-apply`
- apply commands always include `--writeback-apply`
- the command is a recommendation, not an automatic action

## Workbook gate reminder

Use `make workbook-gate` only when you changed workbook-facing code or layout. Normal portfolio use does not require the workbook gate.
