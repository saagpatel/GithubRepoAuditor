# Product Modes

GitHub Repo Auditor now works best when you think about it as one operating system with
four product modes. The flags stay the same underneath; this guide is the shared map for
the docs, CLI help, workbook, HTML, Markdown, review-pack, and scheduled-handoff wording.

As of Arc F Sprint 4.3 the CLI has four subcommands (`run`, `triage`, `report`, `serve`).
Examples below show the subcommand form first. The flat form (`audit <user> --flag`) still
works and shows a deprecation warning. See [docs/audit-cli-migration.md](audit-cli-migration.md)
for the full mapping.

## First Run

Use this mode when you are setting the system up or coming back after a long gap.

If you only want to see the product surfaces before auditing a real account, run the
safe fixture demo first:

```bash
make demo
```

That writes sample JSON, workbook, HTML, and control-center artifacts to
`output/demo/` without a GitHub token.

Recommended path:

```bash
audit run <github-username> --doctor
audit run <github-username> --html
audit triage <github-username> --control-center
```

Goal:
- confirm setup and baseline health
- generate the main workbook and dashboard artifacts
- get the first read-only operator queue

## Weekly Review

Use this mode for the normal ongoing operator loop.

Recommended path:

```bash
audit run <github-username> --html
audit triage <github-username> --control-center
```

Goal:
- refresh the portfolio story
- read the workbook in order
- decide what needs attention now versus what can safely wait

Visible weekly surfaces now share one compact weekly-story contract:
- one headline
- one weekly decision
- one next workflow step
- the same ordered section set across workbook, Markdown, HTML, review-pack, and scheduled handoff

Treat that as a reading aid, not a new queue:
- it does not rewrite `primary_target`
- it does not rewrite `what_to_do_next`
- it keeps the visible weekly story aligned across surfaces

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
audit report <github-username> --campaign <name> --writeback-target github
audit report <github-username> --campaign <name> --writeback-target all --github-projects
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
- `overdue-follow-up` and `due-soon-follow-up` are freshness cues carried through `follow_up_state`, not new approval states

Use that layer as workflow memory, not as execution:
- it records local approval history, recurring follow-up review history, and receipts
- it is surfaced through `--approval-center` plus the `Next Approval Review` line
- it never widens write authority
- it never makes `--writeback-apply` automatic

The visible weekly sections should now read in a stable order:
- `Weekly Priority`
- `Action Sync Readiness`
- `Apply Packet`
- `Post-Apply Monitoring`
- `Campaign Tuning`
- `Historical Portfolio Intelligence`
- `Automation Guidance`
- `Approval Workflow`
- `Operator Focus`

Each section should answer the same three questions quickly:
- what is the current state
- what is the next safe step
- what evidence is driving the call

## Default guidance

- `audit run <user> --doctor` is the recommended first step.
- A GitHub token is optional for public-only audits, but recommended for private repos, higher rate limits, and any mutation/writeback path.
- `--excel-mode standard` is the default and recommended workbook path.
- `audit triage <user> --control-center` is the read-only daily operator entrypoint.
- `template` workbook mode, scorecards config, catalog config, campaigns, writeback, GitHub Projects, and Notion sync are advanced workflows.

---

## Subcommand flag reference

The four subcommands group flags by workflow. All subcommands accept the shared globals
`--token`, `--output-dir`, `--config`, and `--verbose`.

### audit run

Fetch, clone, analyze, and score all repos for the given username.

```
audit run <username> [flags]
```

Key flags:

| Flag | Description |
|------|-------------|
| `--repos REPO [REPO ...]` | Targeted mode — re-audit only these repos |
| `--incremental` | Re-audit only repos with new pushes since last run |
| `--html` | Generate interactive HTML dashboard |
| `--briefing` | Generate structured weekly operator briefing |
| `--narrative` | Generate AI portfolio narrative |
| `--fetch-mode {sync,async}` | Per-repo enrichment strategy (default: sync) |
| `--analysis-workers N` | Parallel analysis workers (default: 1) |
| `--no-cache` | Bypass API response cache |
| `--reindex` | Rebuild portfolio semantic index after audit |
| `--embedder {voyage,local}` | Embedder backend for `--reindex` |
| `--scoring-profile NAME` | Custom scoring profile |
| `--watch` | Re-run audit on interval |
| `--skip-forks` | Exclude forked repos |
| `--skip-archived` | Exclude archived repos |
| `--graphql` | Use GraphQL API for faster bulk fetch |
| `--badges` | Generate Shields.io badge files |
| `--pdf` | Generate PDF audit report |
| `--vuln-check` | Query OSV.dev for known vulnerabilities |
| `--doctor` | Run setup diagnostics only (no audit) |
| `--resume` | Resume a partial audit run |

### audit triage

Inspect control-center, approval queues, acknowledgments, and semantic search.

```
audit triage <username> [flags]
```

Key flags:

| Flag | Description |
|------|-------------|
| `--control-center` | Show latest operator state (read-only) |
| `--approval-center` | Show latest approval workflow state |
| `--triage-view {all,urgent,ready,blocked,deferred}` | Filter control-center output |
| `--approval-view {all,ready,approved,needs-reapproval,blocked,applied}` | Filter approval output |
| `--semantic-search QUERY` | Semantic search against portfolio index |
| `--ask QUERY` | Alias for `--semantic-search` |
| `--auto-apply-approved` | Apply approved packets for repos passing trust bar |
| `--dry-run` | Preview without making changes |
| `--approve-governance` | Capture a governance approval |
| `--approve-packet` | Capture a campaign approval |
| `--review-governance` | Capture a governance follow-up review |
| `--review-packet` | Capture a campaign follow-up review |
| `--reset-prefs` | Clear operator suppression hints |
| `--acknowledge-target REPO` | Repo to acknowledge in review queue |
| `--acknowledge-kind KIND` | Change type to acknowledge |

### audit report

Portfolio truth, Excel workbooks, campaigns, writebacks, and context recovery.

```
audit report <username> [flags]
```

Key flags:

| Flag | Description |
|------|-------------|
| `--portfolio-truth` | Generate canonical portfolio truth snapshot |
| `--portfolio-context-recovery` | Build active/recent weak-context recovery plan |
| `--apply-context-recovery` | Apply eligible context recovery updates |
| `--excel-mode {template,standard}` | Workbook style (default: standard) |
| `--campaign NAME` | Build a managed campaign view |
| `--writeback-target {github,notion,all}` | External system to receive writeback |
| `--writeback-apply` | Execute live writeback (not preview) |
| `--github-projects` | Mirror campaign actions into GitHub Projects v2 |
| `--campaign-sync-mode {reconcile,append-only,close-missing}` | Record strategy |
| `--diff PREVIOUS_REPORT` | Compare against a previous report |
| `--notion-sync` | Push audit events to Notion API |
| `--collection NAME` | Filter outputs to a named collection |
| `--portfolio-profile NAME` | Custom portfolio profile |

### audit serve

Serve portfolio artefacts via a local FastAPI + HTMX web UI.
Requires the `[serve]` extra (`pip install -e '.[serve]'`).
See [docs/audit-serve.md](audit-serve.md) for the full operator guide.

```
audit serve [flags]
```

Key flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--port PORT` | `8080` | Port to listen on |
| `--host HOST` | `127.0.0.1` | Interface to bind |
| `--output-dir DIR` | `./output` | Directory where audit output lives |
