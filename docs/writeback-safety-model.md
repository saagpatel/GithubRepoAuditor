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

## Audit Trail

Every campaign run records:

- the campaign summary
- previewed writes
- apply results
- per-action run status
- campaign lifecycle summary, drift, and rollback availability
- external refs such as GitHub issue URLs or Notion page URLs

Those facts are stored in both the report outputs and the warehouse snapshot so campaign history stays visible even when no repo analysis changed.
