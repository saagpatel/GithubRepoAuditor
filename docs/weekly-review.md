# Weekly Review

Use this guide for the normal ongoing operator loop. If you need the broader product map first, start with [modes.md](/Users/d/Projects/GithubRepoAuditor/docs/modes.md). If something is broken, jump to [operator-troubleshooting.md](/Users/d/Projects/GithubRepoAuditor/docs/operator-troubleshooting.md).

## Weekly cadence

1. Run `audit <github-username> --doctor` if setup, baseline, or workbook health is in doubt.
2. Run `audit <github-username> --html` to refresh the workbook, Markdown, HTML, JSON, review-pack, and scheduled-handoff story.
3. Run `audit <github-username> --control-center` for read-only operator triage from the latest state.
   This also refreshes the report-only `weekly-command-center-<username>-<date>.json` and `.md` digest.
4. Open the workbook and read it in this order:
   - `Dashboard`
   - `Run Changes`
   - `Review Queue`
   - `Portfolio Explorer`
   - `Repo Detail`
   - `Executive Summary`

## How to read the weekly surfaces

The primary workbook, HTML, Markdown, review-pack, and scheduled-handoff surfaces all tell the same compressed operator story:

- `Act Now` means blocked or urgent pressure is active right now.
- `Watch Closely` means the repo is active and deserves attention, but it does not outrank the highest-pressure work yet.
- `Improving` means the path is stabilizing and recent action is helping.
- `Fragile` means progress is real but easy to lose.
- `Revalidate` means confidence still needs to be rebuilt before the repo should be treated as restored.

Read those buckets in exactly that order. The hidden workbook sheets and raw JSON still keep the richer lifecycle detail underneath.

Phase 96 adds one stronger packaging rule on top of that guidance:

- the visible weekly surfaces share one `weekly_story_v1` contract
- each section now carries a compact summary, a next step, and a short evidence strip
- scheduled handoff is part of that same weekly contract instead of inventing a separate weekly story

That means the visible surfaces should agree on:
- the weekly headline
- the weekly decision
- the next workflow step
- the section order
- the short evidence for why a repo, campaign, or approval path is being surfaced

The current release boundary still keeps one shared weekly story, but that story can now apply a bounded approval-aware overlay when local approval work is the best weekly move. That overlay stays inside `weekly_story_v1`: blocked or urgent portfolio pressure still wins, and the product still does not ship a second weekly recommendation engine.

Phase 107 adds one more bounded artifact on top of that same contract: the weekly command-center digest. It is not a second authority and it is not an executor. It is a report-only summary that packages the shared weekly story together with current decision-quality posture and live portfolio-truth/path attention so a paused or future weekly loop can read one structured digest instead of stale hand-maintained notes.

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

If you open the weekly command-center digest, read it after the control-center headline, not instead of it:

1. `Headline`
2. `Decision`
3. `Why This Week`
4. `Path Attention`
5. `Weekly Sections`

The digest is there to compress the weekly read, not to replace the workbook or the control-center artifact.

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

Then read the third shared layer: `Post-Apply Monitoring`.

- `drift-returned` means a managed mirror drifted again after apply and needs review before another sync.
- `reopened` means the lifecycle reopened after apply and the earlier sync did not hold.
- `rollback-watch` means rollback coverage was incomplete or rollback was later used.
- `monitor-now` means the campaign was applied recently and still needs a short follow-up window.
- `holding-clean` means the campaign has enough follow-up history and is currently staying quiet.

That layer is there to answer one question plainly: did the sync actually help, and what is the next human follow-up step?

If two campaigns are otherwise tied, read `Campaign Tuning` last:

- `proven` means recent judged outcomes are clean enough that the campaign should win ties
- `mixed` means keep the recommendation neutral
- `caution` means recent drift, reopen, or rollback-watch history should make the campaign rank later in ties
- `insufficient-evidence` means there still is not enough judged history to bias the recommendation

That overlay is intentionally bounded:
- it never moves a weaker readiness stage ahead of a stronger one
- it never changes queue order or trust behavior
- it only biases which tied campaign should be recommended first, surfaced as `Next Tie-Break Candidate`

If the weekly question becomes “is this repo actually getting better over time?”, read the new historical layer after the Action Sync sections:

- `Historical Portfolio Intelligence` tells the cross-run repo story
- `Relapsing` means recent intervention did not hold and the repo is turning back upward
- `Persistent Pressure` means the repo keeps resurfacing without durable quieting
- `Improving After Intervention` means recent pressure, hotspot direction, or maturity evidence is moving the right way
- `Holding Steady` means earlier pressure has quieted enough to monitor instead of re-escalating

That historical layer is powered by the `Intervention Ledger`. It is descriptive only:
- it does not create a new queue
- it does not change Action Sync precedence
- it helps you decide whether to keep investing attention in the same repo or treat the improvement as real

Read `Automation Guidance` last, after readiness, apply packet, post-apply monitoring, campaign tuning, and historical intelligence:

- `approval-first` means approval review must happen before any execution step should be treated as safe
- `manual-only` means relapse, reopen, drift, or persistent pressure still needs human judgment first
- `preview-safe` means the suggested preview command is the strongest safe next automation step
- `apply-manual` means the apply command can be shown, but it stays human-only
- `follow-up-safe` means only a non-mutating rerun, workbook refresh, control-center pass, or monitoring step is appropriate
- `quiet-safe` means the portfolio is quiet enough that only housekeeping or quiet-run behavior should be automated

That layer is intentionally bounded:
- it never auto-runs `--writeback-apply`
- it does not create a new executor
- it helps the product decide whether a command hint is safe to surface, not whether a mutation should happen automatically

If the next question becomes “does this need approval, re-approval, or explicit manual apply?”, read `Approval Workflow` after automation guidance:

- `needs-reapproval` means the earlier approval no longer matches the current packet or governance fingerprint
- `ready-for-review` means the approval can be reviewed now, but approval still does not mutate anything
- `approved-manual` means approval is current and the next move is still an explicit manual apply
- `blocked` means approval alone cannot help yet because drift, access, or other blockers still exist
- `overdue-follow-up` and `due-soon-follow-up` mean the subject is still approved, but its local review freshness now matters before scheduling pressure should grow around it

Use `audit <github-username> --approval-center` when you want the read-only approval view. Use `--approve-governance` or `--approve-packet` only to capture initial local approval records. Use `--review-governance` or `--review-packet` only to capture recurring local follow-up review. Those actions may regenerate artifacts, but they do not perform external mutation.

## Weekly section order

When the workbook, Markdown, HTML, review-pack, or scheduled handoff shows the compact weekly story, read the sections in this order:

1. `Weekly Priority`
2. `Action Sync Readiness`
3. `Apply Packet`
4. `Post-Apply Monitoring`
5. `Campaign Tuning`
6. `Historical Portfolio Intelligence`
7. `Automation Guidance`
8. `Approval Workflow`
9. `Operator Focus`

The goal is progressive disclosure:
- the top of the weekly story tells you what deserves attention this week
- each later section tells you the next safe step inside its own layer
- the evidence strips let you validate the recommendation without rereading the full raw artifact first

## Workbook gate reminder

Use `make workbook-gate` only when you changed workbook-facing code or layout. Normal portfolio use does not require the workbook gate.
