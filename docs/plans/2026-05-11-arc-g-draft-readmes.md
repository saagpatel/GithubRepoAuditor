# Arc G — Sprint 5: Agentic README authoring (`--draft-readmes`)

**Status:** Sprint 5 / Arc G kickoff. Drafted 2026-05-11, immediately after Arc F merge (`9e0c636`) and `v0.19.0` tag.

**Why now:** Arc F shipped the semantic index (S3.1), operator preference memory (S3.3), LLM cost guard (S3.5), and the local web UI (S4.1) — all of which compose into the most natural next product step: have the LLM write draft READMEs for repos that need them, route the diff through the approval ledger, and let the operator review/edit/approve in the web UI.

This is the first item from the Arc F backlog (line 336 of `docs/plans/2026-05-10-arc-f-expansion-roadmap.md`). Sprint 5 ships this end-to-end. Sprint 6+ items (planner agent, tier tracker) remain in backlog.

---

## Scope

A new flag `audit report --draft-readmes` (also accessible via legacy `audit <user> --draft-readmes`) walks every repo where:

1. README is **stale** (S1.4 `readme_stale=True` — README touched > 5x older than latest code, code touched < 90 days ago), OR
2. README is **missing** entirely, OR
3. README is **trivially short** (< 200 chars excluding badges/headings), OR
4. Operator explicitly opts the repo in via `--draft-readmes-repo <name>` (repeatable)

For each qualifying repo, the LLM authors a draft README using:

- **Repo metadata** — language, topics, stars, latest release notes, license
- **Top-level file tree** — first two directory levels
- **Semantic neighbors** — `SemanticIndex.find_neighbors(repo, k=3)` from S3.1 supplies stylistic context ("repos in this portfolio look like this")
- **Existing README** if present (the LLM should improve, not rewrite, where possible)
- **Recent commit messages** — last 10 commits, subject lines only

The output is a **diff packet** (not a wholesale replacement file) recorded in the approval ledger with `action_type="draft-readme"`. Each packet contains:

```json
{
  "repo_name": "...",
  "action_type": "draft-readme",
  "current_readme_sha": "...",
  "proposed_readme": "...",
  "diff_summary": "Added: install, usage, badges sections",
  "llm_provider": "anthropic|github-models",
  "llm_model": "...",
  "llm_cost_usd": 0.0042,
  "generated_at": "2026-05-11T...",
  "context_repos": ["repo-a", "repo-b", "repo-c"]
}
```

Operator review path:

1. CLI: `audit triage --approval-center --approval-view ready` lists the packets
2. Web UI: `/approvals` page shows each draft with an "expand diff" HTMX action that renders the proposed README beside the current one
3. Approve via existing `approval_request_approve` flow → packet moves to `approved-manual` state
4. Apply via `audit report --apply-readmes` (S4 already wires this for some action types — extend if needed)

---

## Inventory

| # | Item | Status | Notes |
|---|---|---|---|
| 5.1 | `src/draft_readmes.py` module with `qualify_repos()`, `build_context()`, `generate_draft()` | ⏳ | Pure functions, easy to unit-test |
| 5.2 | Wire `--draft-readmes` flag into `audit report` subcommand + legacy flat path | ⏳ | Use existing approval ledger writer (no schema changes) |
| 5.3 | Preference suppression — skip repos where the operator rejected a draft-readme 3+ times | ⏳ | Reuses S3.3 `operator_prefs.detect_suppressions()` |
| 5.4 | Web UI: `/approvals` shows draft-readme packets with side-by-side diff partial | ⏳ | HTMX partial swap, no JS |
| 5.5 | `audit report --apply-readmes` writes approved drafts back via GitHub Contents API | ⏳ | Reuse existing apply path if present, else add minimal one |
| 5.6 | Cost guard integration — abort batch if cumulative LLM spend > `--max-llm-spend` | ⏳ | S3.5 `CostTracker` already wired into providers |
| 5.7 | Tests + docs + Sprint 5 closeout | ⏳ | Final |

---

## Cross-arc principles inherited

From Arc F's three durable lessons:

1. **External-API specs go stale.** When using the GitHub Contents API for README writeback, treat the docs as "as-of-date" and validate against actual response shape.
2. **Module-level state keyed by `id()` is unsafe.** No registration caches keyed by object identity in this sprint.
3. **Subagent worktree branch-base brittleness.** When dispatching, verify the worktree base SHA matches `feat/arc-g-draft-readmes` tip before letting the subagent commit. If the agent reports a test count that doesn't match current, that's the signal of wrong base.

---

## Open questions (resolve at kickoff)

| Q | Default | Notes |
|---|---|---|
| Should we run all qualifying repos by default, or require explicit opt-in like Arc D's automation? | **Opt-in default.** Operator must pass `--draft-readmes-repo <name>` or `--draft-readmes-all`. | Safer; matches Arc D's trust-bar discipline. |
| Provider default — Anthropic or GitHub Models? | **Reuse existing `--narrative-provider` default** (Anthropic if API key set, else GitHub Models). | No new resolution logic. |
| Should drafts be diff-format or full-file replacement? | **Full file as proposed_readme, but show diff in UI.** | Easier to author; UI computes diff at render time. |

---

## Exit criteria

- `audit report --draft-readmes-repo <name>` generates a draft README and writes a packet to the approval ledger
- `audit triage --approval-center --approval-view ready` lists the packet
- Web UI `/approvals` renders the draft beside the current README
- Approve via existing flow → packet moves to `approved-manual`
- `audit report --apply-readmes` writes the approved draft to GitHub
- All 1469 existing tests still pass; +20-40 new tests for the new module
- Sprint 5 closeout appended to this doc with shipped/stopped/lessons
