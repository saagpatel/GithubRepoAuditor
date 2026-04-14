# Product Modes

GitHub Repo Auditor now works best when you think about it as one operating system with four product modes. The flags stay the same underneath; this guide is the shared map for the docs, CLI help, workbook, HTML, Markdown, and review-pack wording.

## First Run

Use this mode when you are setting the system up or coming back after a long gap.

Recommended path:

```bash
audit <github-username> --doctor
audit <github-username> --html
audit <github-username> --control-center
```

Goal:
- confirm setup and baseline health
- generate the main workbook and dashboard artifacts
- get the first read-only operator queue

## Weekly Review

Use this mode for the normal ongoing operator loop.

Recommended path:

```bash
audit <github-username> --html
audit <github-username> --control-center
```

Goal:
- refresh the portfolio story
- read the workbook in order
- decide what needs attention now versus what can safely wait

Primary reading order:
- `Dashboard`
- `Run Changes`
- `Review Queue`
- `Portfolio Explorer`
- `Repo Detail`
- `Executive Summary`

## Deep Dive

Use this mode when one repo needs a real decision instead of a quick portfolio pass.

Typical clues:
- the repo keeps resurfacing
- one implementation hotspot dominates the next move
- the maturity gap is still unclear

Best surfaces:
- `Repo Detail`
- implementation hotspots / `Where To Start`
- scorecard and maturity gap lines
- follow-through checkpoint and operator focus lines

## Action Sync

Use this mode only after the local workbook and control-center story is already settled.

Typical flags:

```bash
audit <github-username> --campaign <name> --writeback-target github
audit <github-username> --campaign <name> --writeback-target all --github-projects
```

Goal:
- preview or apply managed campaign actions
- sync to GitHub, GitHub Projects, or Notion
- keep the local report authoritative while mirroring the decision outward

Action Sync now moves through three layers:
- readiness
- apply packet
- post-apply monitoring

Action Sync readiness now uses one shared reading order:
- `drift-review` first
- `blocked` second
- `apply-ready` third
- `preview-ready` fourth
- otherwise stay local

Use that as the default rule:
- review drift before more syncing
- clear blockers before apply
- only apply when the local story is already settled
- preview next when there is a good campaign but no reason to push yet

Action Sync execution now adds one second layer on top of readiness:
- `review-drift`: stop and review managed drift before you sync anything else
- `needs-approval`: the campaign is close, but governance approval or rollback review still blocks apply
- `ready-to-apply`: the campaign is healthy enough to apply if you choose
- `preview-next`: the campaign is worth previewing next, but the product is still nudging you to stay preview-first
- `stay-local`: there is no safe execution handoff yet

When the product shows an `Apply Packet`, read it as a handoff suggestion:
- preview commands are safe planning commands only
- apply commands always require an explicit manual rerun with `--writeback-apply`
- `ready-to-apply` never means automatic mutation

After preview or apply, use the new post-apply monitoring layer as the third read:
- `drift-returned`: managed drift came back after apply, so review drift before another sync
- `reopened`: the action lifecycle reopened after apply, so the earlier sync did not hold
- `rollback-watch`: rollback coverage was partial or missing, or rollback was later used
- `monitor-now`: the campaign was applied recently and is still inside the short follow-up window
- `holding-clean`: the campaign has enough follow-up runs and is currently staying quiet
- `insufficient-evidence`: some apply evidence exists, but the history is too thin to judge confidently
- `no-recent-apply`: there is no recent apply to monitor yet

Post-apply monitoring is still descriptive:
- it does not trigger another writeback automatically
- it tells you whether the next step is drift review, reopen review, rollback watch, or normal monitoring

Phase 89 adds one bounded recommendation overlay on top of those three layers:
- `Campaign Tuning` only breaks ties when multiple campaigns are already in the same readiness or execution group
- `proven` campaigns win ties
- `caution` campaigns are ranked later in ties
- `insufficient-evidence` stays neutral until enough judged outcomes exist

Use that overlay as a ranking hint, not a new execution layer:
- it never moves a weaker stage ahead of a stronger one
- it never changes queue order or write authority
- it helps the product explain which tied campaign should be recommended first through the `Next Tie-Break Candidate` line

After those Action Sync layers, read the bounded historical layer when you need the longer-run repo story:

- `Historical Portfolio Intelligence` connects recurring operator attention, implementation hotspot recurrence, scorecard direction, and campaign aftermath
- the `Intervention Ledger` is the cross-run source of truth for that historical read
- it tells you whether a repo is `relapsing`, under `persistent-pressure`, `improving-after-intervention`, or `holding-steady`

Use that layer to decide whether the same repo is truly getting better over time or just consuming another week of attention:
- it does not create a new queue
- it does not change readiness or apply precedence
- it complements the current weekly/operator story rather than replacing it

Phase 92 adds one final bounded guidance read after those layers: `Automation Guidance`.

- `approval-first` means approvals must be reviewed before any execution command should be treated as safe
- `manual-only` means relapse, reopen, drift, or persistent-pressure signals still require human judgment first
- `preview-safe` means the strongest safe next move is an explicit preview command
- `apply-manual` means apply is available, but it stays an explicit human-only action
- `follow-up-safe` means only non-mutating follow-up like rerun, workbook refresh, control-center review, or monitoring is appropriate
- `quiet-safe` means the safest automation is housekeeping or quiet-state behavior only

Use that layer as a posture label, not as permission:
- it never auto-runs `--writeback-apply`
- it never changes readiness or execution precedence
- it only tells you whether surfacing a command is safe and bounded

Phase 93 adds one local approval read after that posture layer: `Approval Workflow`.

- `needs-reapproval` means the earlier approval no longer matches the current fingerprint or blocker story
- `ready-for-review` means the approval can be reviewed now, but it still does not apply anything
- `approved-manual` means approval is current and the next step is still an explicit human apply
- `blocked` means non-approval blockers still exist, so approval alone cannot clear the path

Use that layer as workflow memory, not as execution:
- it records local approval history and receipts
- it is surfaced through `--approval-center` plus the `Next Approval Review` line
- it never widens write authority
- it never makes `--writeback-apply` automatic

## Default guidance

- `--doctor` is the recommended first step.
- `--excel-mode standard` is the default and recommended workbook path.
- `--control-center` is the read-only daily operator entrypoint.
- `template` workbook mode, scorecards config, catalog config, campaigns, writeback, GitHub Projects, and Notion sync are advanced workflows.
