# Arc G — Sprint 6: Campaign planner agent (`--plan-campaign "goal"`)

**Status:** Sprint 6 / Arc G. Drafted 2026-05-12, immediately after Sprint 5 (`--draft-readmes`, PR #162) and the post-merge serve bugfix (PR #164).

**Why now:** Existing campaigns (`security-review`, `promotion-push`, `archive-sweep`, `showcase-publish`, `maintenance-cleanup`) are pre-defined — the operator picks one off a menu. Sprint 6 inverts this: the operator describes a goal in natural language, and the LLM authors a structured campaign of actions across qualifying repos. The packets flow through the existing approval ledger so trust-bar discipline is preserved end-to-end.

This is item 2 from the Arc F backlog (line 337 of `docs/plans/2026-05-10-arc-f-expansion-roadmap.md`). Composes every prior Arc F+G capability:

- Semantic index (S3.1) → relevant-repo retrieval for the goal
- Operator preference memory (S3.3) → suppress repeatedly-rejected action types
- LLM cost guard (S3.5) → batch halts on budget exceed
- Approval ledger (Arc D) → packets flow through standard approve/reject/apply
- Web UI (S4.1) → operator reviews the campaign in `/approvals` with action-by-action breakdown
- Writeback path (Arc D + S5.5) → approved actions apply via existing `--writeback-apply`

---

## Scope

A new flag `audit report --plan-campaign "GOAL"` walks the portfolio:

1. **Goal parsing** — operator passes a freeform string: e.g. `"archive all dead Tauri experiments older than 1 year"` or `"add MIT LICENSE to every public repo that's missing one"`.
2. **Candidate retrieval** — the planner uses `SemanticIndex.search(goal, k=20)` (when an index exists) plus deterministic filters from the goal's parsed intent (language, age, license, tier) to narrow the candidate set.
3. **Per-repo evaluation** — for each candidate, the LLM is asked "does this repo qualify for the goal, and if so, what specific action should be taken?". Output is a structured `CampaignAction`.
4. **Plan packet** — the full list of `CampaignAction`s plus a goal summary, total cost, and run metadata is written to the approval ledger as a single packet with `approval_subject_type="campaign-plan"`.
5. **Review path** — `/approvals` shows the packet with a per-repo action breakdown (HTMX-expandable, like Sprint 5's draft-diff). Approve/reject is all-or-nothing for v1.
6. **Apply path** — approved packets feed into `--writeback-apply --campaign-from-ledger` which executes each action via the existing pre-built action handlers (archive via GitHub Archive API, README writeback via Contents API, etc.).

**Important constraint:** action types are NOT free-form. They must map to one of the existing executable actions (`archive`, `unarchive`, `add_license`, `add_topics`, `update_description`, `apply_readme`, `add_codeowners`, `enable_dependabot`). If the LLM proposes anything else, it goes in the packet as `pending_human_action` (no auto-apply path, just a TODO for the operator).

---

## Inventory

| # | Item | Status | Notes |
|---|---|---|---|
| 6.1 | `src/plan_campaign.py` core module with `parse_goal()`, `narrow_candidates()`, `generate_plan()`, `write_packet()` | ⏳ | Pure functions; mockable provider for tests |
| 6.2 | Wire `--plan-campaign "GOAL"` into `audit report` subcommand + legacy flat path | ⏳ | Reuse `_resolve_provider()` from S1.2 |
| 6.3 | Web UI: `/approvals` shows campaign-plan packets with per-action HTMX-expandable breakdown | ⏳ | Reuses S5.4 partial pattern |
| 6.4 | Apply path: `--writeback-apply --campaign-from-ledger` hook into existing action executors | ⏳ | Each `CampaignAction` dispatched to its handler |
| 6.5 | Tests + Sprint 6 closeout | ⏳ | Final |

---

## Schema

```python
@dataclass(frozen=True)
class CampaignAction:
    repo_name: str
    action_type: Literal["archive", "unarchive", "add_license", "add_topics",
                          "update_description", "apply_readme", "add_codeowners",
                          "enable_dependabot", "pending_human_action"]
    target: str  # e.g. license SPDX, topic list, description text, README path
    rationale: str  # ~1-sentence LLM explanation
    expected_impact: str | None = None

@dataclass(frozen=True)
class CampaignPlanPacket:
    goal: str
    actions: list[CampaignAction]
    candidate_count: int
    qualified_count: int
    llm_provider: str
    llm_model: str
    llm_cost_usd: float
    generated_at: str
```

Packet flows through the approval ledger via:
- `approval_subject_type = "campaign-plan"`
- `subject_key = <stable hash of goal text>` (e.g. first 16 chars of `sha256(goal)`)
- `details_json` contains the full packet

---

## Constraints inherited from prior arcs

1. **Schema-as-implemented beats schema-as-specified** (S5 Lesson 1). Adapt to whatever `approval_subject_type` / `subject_key` columns the warehouse actually has.
2. **Subagent worktree base-SHA discipline** (Arc F Lesson 3 + S5 Lesson 2). Each subagent verifies base SHA before doing anything.
3. **Boot tests catch CLI wiring bugs** (S4 Lesson 2 + S5 reinforced after PR #164). Every new CLI mode gets a one-line "process boots, exit cleanly on missing inputs" smoke baked into the verification step.
4. **No auto-apply without explicit trust-bar gate.** Approved campaign packets still require `--writeback-apply` to actually execute. No silent application.

---

## Open questions (resolve at kickoff)

| Q | Default | Notes |
|---|---|---|
| Should approve/reject be all-or-nothing or per-action? | **All-or-nothing for v1.** Per-action review is Sprint 7. | Keep the v1 UI simple; if the plan has 30 actions and you only want 25, you reject and re-run with refinements. |
| Should `--plan-campaign` write a packet even if 0 actions qualified? | **Yes.** Writes packet with `qualified_count=0` so the operator can see what was attempted. | Useful negative signal. |
| Should the LLM be allowed to propose multiple actions per repo? | **One action per repo for v1.** Multi-action repos go in as `pending_human_action`. | Simpler routing; multi-action is Sprint 7. |
| If no semantic index exists, should the planner fall back to scanning all repos? | **Yes, with a `--max-repos N` cap (default 50)** to bound cost. | Same fallback pattern as Sprint 5's `qualify_repos`. |

---

## Exit criteria

- `audit report --plan-campaign "archive abandoned experiments"` generates a packet and writes it to the ledger
- `audit triage --approval-center --approval-view ready` lists the campaign-plan packet
- Web UI `/approvals` renders the packet with the goal text and per-action expandable list
- Approve via existing flow → packet moves to `approved-manual`
- `audit report --writeback-apply --campaign-from-ledger` executes each `CampaignAction` via the existing action handlers
- All 1508 existing tests still pass; +25-40 new tests
- Sprint 6 closeout appended to this doc
- Boot test included in verification: `audit report --plan-campaign "test" --dry-run someuser` exits cleanly when truth file is missing
