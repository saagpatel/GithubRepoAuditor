# Writeback Safety Model

This phase turns audit recommendations into operational actions, but it does so with narrow guardrails.

## What Is Managed

- GitHub topics that start with the reserved `ghra-` prefix
- One managed GitHub issue per repo per campaign type
- Org custom property values, but only when the property definitions already exist
- Managed Notion action and campaign records when the workspace schema supports them

Everything else remains outside the tool's write authority in this phase.

## Governed Security Controls

The operator surfaces may now carry lifecycle and rollback facts for governed GitHub security controls when that context is present in the report:

- repository `security_and_analysis` controls
- CodeQL default setup

Those controls are still manual and opt-in. Approval/apply state, drift, and rollback coverage are mirrored into the report and warehouse, but the tool does not widen authority into rulesets, branch protection, or repo-content mutation in this phase.

## What Stays Preview-Only

- Rulesets and branch protection
- Other repo/security setting mutations that require repo-content or policy changes
- Any repo-content mutation outside the managed campaign surfaces below

Those still appear in governance previews, but the tool does not apply them automatically.

## Idempotency Rules

- Every executable action gets a stable `action_id`
- GitHub issues use a hidden managed marker in the body so reruns update instead of duplicate
- Managed topics only add or remove `ghra-*` values and preserve all user-owned topics
- Notion action sync is keyed to the same stable action IDs when the workspace schema supports them
- Campaign sync modes control whether stale managed records are reconciled, left alone, or explicitly closed
- When a repo re-enters a campaign, the system prefers reopening the existing managed issue or Notion record instead of creating a duplicate

## Rollback Model

- Managed topics and custom properties restore the last recorded managed values
- Managed GitHub issues revert by updating or closing the managed issue, not by touching unrelated issues
- Managed Notion actions roll back by moving to a cancelled or archived state rather than deleting records
- Rollback is keyed to one prior campaign run and is idempotent on managed surfaces only

## Drift Detection

- Missing managed issues or Notion pages are surfaced as drift
- Unexpected edits to managed issue title/body are surfaced as drift before overwriting
- Missing or stale `ghra-*` topics and custom-property mismatches are recorded in the audit trail
- Governance approval or control-state mismatches are surfaced separately as governance drift when that context exists
- Drift is shown in JSON, Excel, HTML, Markdown, and review-pack outputs so operators can decide whether to apply or review first

## Apply Packets

Phase 87 adds one explicit execution handoff on top of readiness. Each managed campaign can now surface an `Apply Packet` with:

- the current execution state
- the strongest blocker types
- rollback readiness
- the exact preview command to run next
- the exact apply command to run next when the campaign is truly safe

Execution states are intentionally narrow:

- `review-drift`: human review comes first because managed drift is already present
- `needs-approval`: governance approval or rollback review still blocks apply
- `ready-to-apply`: the campaign is healthy enough that apply is now a reasonable manual choice
- `preview-next`: preview is the right next step, but apply would still be premature
- `stay-local`: keep the story local for now

`ready-to-apply` does not widen authority and does not trigger automatic mutation. It only means the product can now hand you a concrete command suggestion with fewer unresolved safety concerns.

## Post-Apply Monitoring

Phase 88 adds a third layer after readiness and apply-packet handoff: post-apply monitoring.

That layer answers whether a recent campaign apply:

- stayed clean
- drifted again
- reopened work
- needs rollback watch
- still needs a short follow-up window

The monitoring states are intentionally narrow:

- `drift-returned`: managed drift reappeared after apply
- `reopened`: lifecycle later reopened after apply
- `rollback-watch`: rollback coverage was partial or missing, or rollback was later used
- `monitor-now`: apply happened recently and still needs follow-up runs
- `holding-clean`: enough post-apply runs exist and the campaign is currently holding
- `insufficient-evidence`: some evidence exists, but the history is still too thin to judge cleanly
- `no-recent-apply`: there is no recent apply to monitor

Post-apply monitoring is descriptive only. It does not trigger another sync, rollback, or mutation by itself. It exists to keep the operator loop honest after execution.

## Campaign Tuning

Phase 89 adds a bounded recommendation overlay on top of readiness, apply packets, and post-apply monitoring.

This bounded overlay uses observed post-apply track record to bias tied recommendations only:

- `proven` campaigns can win ties
- `mixed` campaigns stay neutral
- `caution` campaigns should be ranked later in ties
- `insufficient-evidence` stays neutral until enough judged outcomes exist

This layer does not widen authority:

- it does not create a new execution state
- it does not change queue order, scoring, or trust policy
- it does not move a weaker readiness or execution stage ahead of a stronger one
- it does not trigger automatic preview, apply, or rollback
- it is surfaced to operators as `Campaign Tuning` plus `Next Tie-Break Candidate`

## Automation Guidance

Phase 92 adds one bounded automation-posture layer on top of readiness, apply packets, post-apply monitoring, campaign tuning, and historical portfolio intelligence.

The automation postures are intentionally narrow:

- `approval-first`: approval or governance review must happen before any execution step should be treated as safe
- `manual-only`: drift, reopen, relapse, or persistent-pressure signals still require human judgment first
- `preview-safe`: an explicit preview command is the strongest safe next step
- `apply-manual`: an apply command may be shown, but it remains an explicit human-only action
- `follow-up-safe`: only non-mutating follow-up such as rerun, workbook refresh, control-center review, or monitoring is appropriate
- `quiet-safe`: only quiet-state or housekeeping automation is appropriate

This layer does not widen authority:

- it never auto-runs `--writeback-apply`
- it does not create a new executor or background mutation path
- it does not override stronger readiness, execution, monitoring, tuning, or historical-intelligence signals
- it exists to keep surfaced execution guidance bounded and honest

## Approval Workflow

Phase 93 adds one local approval layer on top of the existing execution story.

Approval states are intentionally narrow:

- `needs-reapproval`: the earlier approval no longer matches the current fingerprint or blocker set
- `ready-for-review`: approval can be reviewed now, but no mutation happens yet
- `approved-manual`: approval matches the current fingerprint and the next move is still an explicit manual apply
- `blocked`: approval alone cannot help yet because drift, access, or other blockers still exist
- `applied`: a matching approved subject has already been manually applied

This layer does not widen authority:

- approval capture records a local attestation only
- recurring follow-up review records a separate local review event only
- it may regenerate workbook, Markdown, HTML, review-pack, control-center, and approval-center artifacts
- it never performs external mutation
- it never auto-runs `--writeback-apply`
- campaign approvals are limited to approval-eligible packets; access/config blockers remain blocked rather than approvable

Follow-up freshness is additive:

- `approval_state` still describes validity and apply posture
- `follow_up_state` describes whether the latest approved subject is overdue for local review, due soon, or still fresh enough to stay quiet
- recurring follow-up review uses `--review-governance` or `--review-packet`; it does not replace the initial `--approve-*` capture commands

## Audit Trail

Every campaign run records:

- the campaign summary
- previewed writes
- apply results
- per-action run status
- campaign lifecycle summary, drift, and rollback availability
- external refs such as GitHub issue URLs or Notion page URLs

Those facts are stored in both the report outputs and the warehouse snapshot so campaign history stays visible even when no repo analysis changed.
