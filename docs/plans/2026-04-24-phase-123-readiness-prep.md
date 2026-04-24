# Phase 123 Readiness Prep - 2026-04-24

## Status

Phase 123 is still not ready for live automated apply.

Fresh checks from `main` at `e5fc2d7`:

- `python3 -m src saagpatel --portfolio-truth --registry-output output/project-registry.md --portfolio-report-output output/PORTFOLIO-AUDIT-REPORT.md`
  - Generated `output/portfolio-truth-latest.json` for 115 projects.
  - Current automation opt-ins: `0`.
- `python3 -m src saagpatel --approval-center`
  - No current approval needs review.
  - Wrote `output/approval-center-saagpatel-2026-04-24.json` and `.md`.
- `python3 -m src saagpatel --auto-apply-approved --dry-run`
  - No `approved-manual` campaign packets found.

## Current Gates

Live apply remains blocked until all three trust-bar inputs exist:

1. At least 2-3 intentionally selected repos have `automation_eligible: true` in `config/portfolio-catalog.yaml`.
2. A bounded campaign packet exists and is approved through the local approval workflow.
3. `--auto-apply-approved --dry-run` shows eligible actions and expected receipts before any live apply.

## 2026-04-24 Opt-In Pass

The first manual opt-in pass selected the primary shortlist:

- `mcpforge`
- `TradeOffAtlas`
- `TideEngine`

`config/portfolio-catalog.yaml` now marks those three repos with `automation_eligible: true`. A regenerated portfolio-truth snapshot confirmed exactly 3 automation-eligible projects, all with baseline risk, high path confidence, full context, and no warnings.

Follow-up gate results:

- `python3 -m src saagpatel --campaign security-review --writeback-target github` was stopped after it stayed silent for several minutes during full-portfolio analysis while holding GitHub HTTPS connections.
- `python3 -m src saagpatel --repos mcpforge TradeOffAtlas TideEngine --campaign security-review --writeback-target github --max-actions 10` completed successfully as a targeted audit.
- The completed `security-review` preview still produced a portfolio-level packet for 10 repos: `AuraForge`, `SlackIncidentBot`, `prompt-englab`, `RedditSentimentAnalyzer`, `IncidentWorkbench`, `OPscinema`, `PersonalKBDrafter`, `StatusPage`, `WorkdayDebrief`, and `visual-album-studio`.
- Approval center still reported no current approval needs review.
- `--auto-apply-approved --dry-run` still reported no approved-manual campaign packets.

Do not live-apply from this state. The next safe implementation step is to make the campaign packet generation or approval flow explicitly show the automation-eligible subset before capturing any local campaign approval.

## Candidate Shortlist

These are candidates for manual opt-in review, not automatic opt-ins. They currently have baseline risk, high path confidence, active or recent activity, full context, and no portfolio-truth warnings:

| Project | Stack | Activity | Why candidate-worthy |
| --- | --- | --- | --- |
| `mcpforge` | Python | active | Full context, active registry status, baseline risk, high path confidence. |
| `TradeOffAtlas` | React, TypeScript, Tauri 2 | active | Full context, active registry status, baseline risk, high path confidence. |
| `TideEngine` | Swift | active | Full context, active registry status, baseline risk, high path confidence. |

Secondary candidates if one of the first three is rejected:

- `RoomTone`
- `Recall`
- `SignalDecay`

## Safe Prep Sequence

1. Manually choose the first 2-3 repos to opt into automation.
2. Add `automation_eligible: true` only to those repo entries in `config/portfolio-catalog.yaml`.
3. Regenerate portfolio truth:

   ```bash
   python3 -m src saagpatel --portfolio-truth --registry-output output/project-registry.md --portfolio-report-output output/PORTFOLIO-AUDIT-REPORT.md
   ```

4. Preview a bounded campaign packet, starting with the lowest-risk campaign that has useful local actions:

   ```bash
   python3 -m src saagpatel --campaign security-review --writeback-target github
   ```

5. Review the approval center:

   ```bash
   python3 -m src saagpatel --approval-center
   ```

6. Only after the packet is intentionally approved, run:

   ```bash
   python3 -m src saagpatel --auto-apply-approved --dry-run
   ```

7. Live apply remains blocked until the dry run shows exactly the expected repo/action set.

## Not Done Here

- No campaign packet was approved.
- No writeback apply or auto-apply live command was run.
- Manual desktop Excel signoff for the 2026-04-24 workbook remains outside this prep note.
