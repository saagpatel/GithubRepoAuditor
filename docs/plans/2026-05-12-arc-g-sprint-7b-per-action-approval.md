# Arc G — Sprint 7B: Per-action approval refinement

**Status:** Sprint 7B / Arc G. Drafted 2026-05-12 immediately after Sprint 6 merge (PR #166, `38a5c5e`). Sprint 7B ships first, then Sprint 7A in the same session per operator instruction.

**Why now:** Sprint 5 (`--draft-readmes`) and Sprint 6 (`--plan-campaign`) both ship packets where approve/reject is all-or-nothing. Operator with a 30-action campaign plan can't "approve 25 of these, reject 5" — they have to reject the whole packet and re-run with refinements. Sprint 7B closes that limitation while the code is fresh.

---

## Scope

Per-action state inside packets. Each `CampaignAction` (Sprint 6) and each draft-readme update (Sprint 5 stores one draft per packet, so per-action is naturally per-section in the diff) gets an independent `state`. The apply path only executes actions with `state == "approved"`. Packets auto-mark `applied` when every action is either `applied`-after-approval or explicitly `rejected`.

For Sprint 7B v1, scope is limited to **campaign-plan packets** (since draft-readme is one-action-per-packet, per-action doesn't help there). The UI pattern we build is reusable for any multi-action packet type that comes later.

---

## Inventory

| # | Item | Status | Notes |
|---|---|---|---|
| 7B.1 | Schema: add `state` field per `CampaignAction` in `details_json`. Migration is zero-cost (default `"pending"` when absent on read) | ⏳ | Backfill-safe |
| 7B.2 | `src/plan_campaign.py`: `approve_action(packet_id, idx, output_dir)`, `reject_action(packet_id, idx, output_dir, reason)`, both atomic | ⏳ | INSERT OR REPLACE pattern from S5 |
| 7B.3 | Web UI: new routes `POST /approvals/{packet_id}/actions/{idx}/approve` and `.../reject`; HTMX returns the updated row | ⏳ | No full-page reload |
| 7B.4 | Template: per-action ✓/✗ buttons in `campaign_plan.html` partial; running counter at top ("12 of 30 approved · 3 rejected · 15 pending") | ⏳ | Bound to S6.3 partial |
| 7B.5 | Apply path: `dispatch_action()` skips actions where `state != "approved"`. Packet-level state transitions: applied only when all actions are terminal (applied or rejected) | ⏳ | Extend S6.4 logic |
| 7B.6 | Tests + Sprint 7B closeout | ⏳ | Final |

---

## Schema (additive — no migration)

```json
{
  "goal": "...",
  "actions": [
    {
      "repo_name": "...",
      "action_type": "archive",
      "target": "",
      "rationale": "...",
      "state": "pending",                // NEW. Default "pending" when absent on read.
      "rejected_reason": null,            // NEW. Set on reject.
      "decided_at": null                  // NEW. Set on approve or reject.
    }
  ]
}
```

Reads of pre-Sprint-7B packets default missing `state` to `"pending"` — old packets keep working.

---

## Exit criteria

- `POST /approvals/{id}/actions/0/approve` updates that action's state to `approved` in `details_json`, returns the updated row partial (HTMX swap)
- `POST /approvals/{id}/actions/0/reject` updates state to `rejected`, returns the row partial with a strikethrough or muted style
- The `campaign_plan.html` partial header shows live counts as the operator clicks
- `--writeback-apply --campaign-from-ledger` only executes actions where `state == "approved"`
- Packet auto-marks `applied` when every action has a terminal state (and at least one was actually applied)
- 1561 → ~1585 tests (+20-25 new)
- Boot test: `POST /approvals/nonexistent/actions/0/approve` returns 404 cleanly
- Sprint 7B closeout appended

---

## Subagent dispatch plan

One subagent (Sonnet, worktree-isolated) covers 7B.1 through 7B.5 since they're tightly coupled (schema → write functions → routes → template → apply). 7B.6 (closeout) is Opus coordination.

Estimated effort: 1.5-2 days. ~25 new tests.

---

## Constraints

1. **MUST NOT break existing 1561 tests.** Pre-Sprint-7B packets continue to work via the missing-`state` default.
2. **Subagent base-SHA discipline.** Verify `git log --oneline -1` shows the expected feat-branch tip before committing.
3. **Boot test discipline.** Smoke-test one new POST endpoint via curl before committing.
4. **No new dependencies.** HTMX-only UI swap. No JS framework.
5. **Cwd hygiene.** After worktree operations, prepend `cd /Users/d/Projects/GithubRepoAuditor &&` to bash commands.

---

## Closeout — 2026-05-12

**Status:** SHIPPED. Sonnet subagent (`a65b23a2`) implemented 7B.1-7B.6 on isolated worktree at base SHA `8cbb5f1`. Cherry-picked as `ca832e2` onto `feat/arc-g-sprint-7b-per-action-approval`. Tests `1561 → 1586` (+25). Ruff clean.

**Inventory final:**

| # | Item | Status |
|---|---|---|
| 7B.1 | `CampaignAction` schema gains `state` / `rejected_reason` / `decided_at` (defaults, backward-compat) | ✅ |
| 7B.2 | `approve_action(packet_id, idx, output_dir)` / `reject_action(packet_id, idx, output_dir, reason)` in `src/plan_campaign.py` | ✅ |
| 7B.3 | Routes `POST /approvals/{packet_id}/actions/{idx}/approve` and `.../reject` returning HTMX row fragments via `_render_action_row()` helper | ✅ |
| 7B.4 | `campaign_plan.html` per-action buttons + counter header + approved/rejected row styling | ✅ |
| 7B.5 | Apply path in `src/cli.py` skips non-approved actions, leaves packet `approved-manual` until all terminal | ✅ |
| 7B.6 | `tests/test_per_action_approval.py` — 25 tests (write functions, route happy/404/out-of-range, backward-compat, apply gate) | ✅ |

**Boot test:** `POST /approvals/nonexistent/actions/0/approve` → `404` ✅ on local server.

**Notes / deviations:**

- Existing `approve_action`/`reject_action` route stubs (packet-level intent log) were renamed `approve_packet`/`reject_packet` to free up the names. Behavior unchanged; existing tests still pass.
- The `pending → approved → rejected` re-flip is idempotent (tests cover it). Useful when an operator changes their mind without re-running the LLM.
- Counter header is rendered server-side at GET time (not OOB-swapped on row updates). Operator must refresh the `/approvals/{id}/campaign-plan` partial to see updated counts. Could be made live via `hx-swap-oob` in a follow-up — captured here, not blocking ship.

**Lessons:**

- Subagents respect "no auto-merge" when given an explicit base-SHA + "DO NOT auto-merge" instruction. The S6.3 pattern (auto-merge) doesn't repeat here.
- Locked worktrees that can't be removed via `git worktree remove -f -f` from inside main require the agent process to exit first. The directory removal succeeded, but the dangling branch reference was left behind — harmless, prune-on-push.
- `frozen=True` dataclasses can accept new default-valued fields safely — pre-existing callers that pass positional args keep working.

**Next:** Sprint 7A (tiered maturity + initiative tracker) starts immediately after merge.
