# Operator OS Product Brief

## Strongest Narrative

Operator OS is a local-first control plane for AI-assisted builders.

It turns a sprawling repo portfolio and multiple coding agents into verified truth, visible risk, and one operator-approved next move.

## Product Wedge

The first public wedge is Portfolio Command Center, a desktop command center over GitHub Repo Auditor's portfolio truth snapshot.

This wedge is strong because it is concrete:

- developers understand repo sprawl immediately;
- the data can be fixture-backed for public demos;
- the value is visible in under 90 seconds;
- the trust model can be explained without exposing private personal systems.

## Target Users

- AI-native solo builders with many active and abandoned repos.
- Staff engineers coordinating experiments, internal tools, and production-adjacent prototypes.
- Engineering leaders who need a decision-ready view of project risk and readiness.
- Devtools teams exploring human-supervised agent workflows.

## Jobs To Be Done

- "Tell me which projects are worth attention this week."
- "Show me where risk is building before it becomes an incident."
- "Help me know whether agent-created work is actually verified."
- "Give me one next move without hiding the evidence."
- "Let me use AI agents without giving them silent authority over real systems."

## Product Pillars

1. **Truth before advice**
   Generated artifacts and local checks outrank memory, transcripts, and summaries.

2. **Operator-approved movement**
   Risky actions stay dry-run-first, reviewable, and explicitly approved.

3. **Private by default**
   Local operating data stays local. Public demos use fixtures or sanitized data.

4. **Multi-agent clarity**
   Advisory models advise. Local execution agents verify. The operator decides.

5. **One next move**
   The interface should reduce noise into a decision, not produce another dashboard to babysit.

## What Is Uniquely Hard To Copy

- A canonical portfolio truth contract feeding JSON, Markdown, workbook, HTML, and desktop surfaces.
- Follow-through state that tracks whether recommendations were attempted, stale, recovering, or retired.
- Explicit stale-state handling and restart-safe handoffs.
- Dry-run-first approval gates across repo, Notion, and workflow surfaces.
- Local/private operation with public-safe proof packages.
- Real usage across Codex, Claude Code, ChatGPT Pro, bridge state, notifications, and personal operations without blurring ownership.

## Too Private To Productize Directly

- Personal email, calendar, Drive, task, approval, and daemon state.
- Raw SecondBrain captures and conversation exports.
- Live bridge-db SQLite state, handoffs, recall logs, and shipped-sync receipts.
- Notification logs, Slack routing, and local queue state.
- Notion database rows, page IDs, tokens, and live write receipts.
- Codex sessions, secrets, memories, hook state, and machine-local SQLite databases.
- Real private repo security posture unless explicitly sanitized.

## Public Demo

Use fixture-backed Portfolio Command Center:

1. Generate fixture artifacts with `make demo`.
2. Open Portfolio Command Center against `output/demo`.
3. Show five frames: Portfolio, Risk + Security, Burndown, Trends, Weekly Digest.
4. Close on the Operator OS thesis.

The public demo should not require GitHub tokens, Notion tokens, bridge-db, personal-ops, SecondBrain, notification-hub, or local private logs.

## MVP Product Package

- `CASE-STUDY.md`: the public case study.
- `DEMO-PLAN.md`: the recording and safety plan.
- `docs/demo-proof/public-fixture/`: machine-readable proof package for public demo safety.
- PortfolioCommandCenter README: live mode and public fixture mode clearly separated.
- GitHub Repo Auditor fixture data: repeatable public artifact generation.

## Future Directions

- A hosted static fixture demo that never touches local data.
- A sanitized sample portfolio generator.
- A web-first viewer for the same portfolio truth contract.
- A plugin model for organization-specific analyzers.
- An explicit "agent provenance" schema for which agent touched which repo and with what verification.
- A trust dashboard for dry runs, approvals, and follow-through outcomes.
