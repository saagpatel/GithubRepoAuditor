# Manual Approval Packet Workflow - 2026-05-09

## Status

This note defines the current manual approval-packet workflow for the next Action Sync lane. It is an operating contract, not an approval receipt.

Current May 9 state:

- The latest control-center output says everything currently surfaced is safe to defer.
- The approval center has no `ready-for-review`, `approved-manual`, `needs-reapproval`, or `blocked` packet approvals.
- Action Sync is preview-ready, not apply-ready.
- The current strongest safe automation step is a preview of `security-review`.
- No live writeback is authorized by this note.

## Operating Boundary

Keep these four steps separate:

1. Preview builds the packet and writes local artifacts.
2. Local approval records a reviewer attestation for one current packet fingerprint.
3. Auto-apply dry run proves the approved packet still passes the trust bar.
4. Live apply requires a fresh, explicit operator decision and `--writeback-apply`.

Local approval does not apply anything. It also does not grant background permission for future packets, changed fingerprints, or different campaigns.

## When To Use This Workflow

Use this workflow only after a current audit/control-center cycle shows:

- no blocked or urgent operator queue items for the affected action lane
- a campaign preview exists for the exact campaign under review
- the approval center surfaces a specific `ready-for-review` packet
- the packet fingerprint is stable after the latest preview
- rollback/reconcile posture is visible in the preview artifacts
- the target systems are intentionally selected

Prefer `--writeback-target github` for the first live lane unless Notion configuration is intentionally fixed and reviewed. `--writeback-target all` is useful for previewing the full story, but it should not be treated as live-apply permission.

## Current Recommended Path

Do not capture a packet approval yet. The latest approval center says no current approval needs review.

The next safe move is another preview-only packet generation, starting with the currently recommended lane:

```bash
python3 -m src saagpatel --campaign security-review --writeback-target all
python3 -m src saagpatel --approval-center --approval-view ready
```

If the approval center still shows no ready packet, stay local and keep the operator loop quiet. If it surfaces a ready packet, review the generated campaign artifacts before approval.

2026-05-10 diagnostic update:

- A campaign can be `apply-manual` without having an approval-center packet. That means the preview path is healthy, but the next step is a separate explicit manual apply decision, not `--approve-packet`.
- Approval center now distinguishes this state in its full view as `No Approval Needed` while keeping `--approval-view ready` empty until a true approval-gated packet exists.
- `security-review` is currently in that manual-apply-only lane; do not treat the empty ready queue as a stall.

## Approval Evidence Checklist

Before running `--approve-packet`, confirm:

- the campaign name matches the packet being reviewed
- the approval center shows the packet as `ready-for-review`
- the preview action count, repo count, and top repos match expectations
- there is no unexpected drift, access blocker, or rollback blocker
- the writeback target is deliberate and bounded
- known optional setup gaps are understood
- the approval note names the exact packet and says no live apply is authorized

Example approval shape, with campaign and note adjusted to the reviewed packet:

```bash
python3 -m src saagpatel \
  --campaign security-review \
  --approve-packet \
  --approval-reviewer local-operator \
  --approval-note "Approved the current security-review packet fingerprint after preview review; no live apply authorized here."
```

## Post-Approval Gate

After local approval, rerun the read-only checks:

```bash
python3 -m src saagpatel --approval-center
python3 -m src saagpatel --auto-apply-approved --dry-run
```

Only consider live apply when the dry run shows exactly the expected eligible actions and no new blockers. The live command still requires a separate explicit operator decision.

## Stop Conditions

Do not approve or apply when:

- the approval center has no ready packet
- the preview contains more repos or actions than expected
- the packet includes a repo that lacks the intended automation eligibility
- decision quality is `use-with-review` or otherwise below the trust bar
- drift/reopen/rollback-watch signals are present for the packet
- Notion is included in the live target while Notion setup remains unconfigured
- the operator cannot explain the expected external mutations in one sentence

## Where This Heads

The near-term goal is not broad automation. It is one clean preview-to-approval-to-dry-run rehearsal that proves the operator loop can carry a packet safely without widening write authority.

Once that is stable, the next expansion path is:

1. choose one low-risk campaign packet
2. capture one local approval for the current fingerprint
3. prove the auto-apply dry run selects only the expected actions
4. run live apply only after a fresh explicit decision
5. monitor the post-apply state before adding more campaigns or targets
