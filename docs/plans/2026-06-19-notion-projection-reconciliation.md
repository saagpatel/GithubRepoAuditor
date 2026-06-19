# Notion Projection Reconciliation - 2026-06-19

## Verified Current State

- Canonical truth source: `output/portfolio-truth-latest.json`
  - `generated_at`: `2026-06-19T05:48:13.055063+00:00`
  - project count: 136
  - Notion context rows: 142
- Legacy audit report: `output/audit-report-saagpatel-2026-06-19.json`
  - `generated_at`: `2026-06-19T07:46:41.857483+00:00`
  - audited repo count: 149
- Local Notion projection snapshot after approved row creation: `/Users/d/.local/share/notion-os/project-snapshot.json`
  - generated on 2026-06-19
  - project count: 143
- `cross-system-smoke` `contract-health` now passes.
  - Latest verified run: `2026-06-19T07-47-01Z-81813`
  - `C2-truth-artifact-parity`: PASS, audit report and truth are both current
    on 2026-06-19; truth-only divergence is now 0.
  - `C7-notion-projection`: PASS, snapshot 143 projects vs truth 136,
    projection policy explains 4 Notion-only rows and 2 truth-shadow rows.
  - `C8-projection-policy-contract`: PASS on `notion_projection_policy.v2`.
- Remaining unexpected projection drift: none.

## Completed Live Row Creation

Approved and created in `Local Portfolio Projects` on 2026-06-19:

- `agent-bridge`
- `cross-provider-egress-guard`
- `machine-control-tower`
- `mcp-trust`
- `fable-outputs`

The local Notion snapshot refresh then moved C7 from seven truth-only rows to
two deferred/policy rows.

## Row Classification

| Truth row | Verified truth state | Notion evidence | Recommended disposition |
| --- | --- | --- | --- |
| `agent-bridge` | active, high criticality, `saagpatel/agent-bridge` | created 2026-06-19 | resolved |
| `cross-provider-egress-guard` | active, high criticality, `saagpatel/cross-provider-egress-guard` | created 2026-06-19 | resolved |
| `machine-control-tower` | active, high criticality, `saagpatel/machine-control-tower` | created 2026-06-19 | resolved |
| `mcp-trust` | active, high criticality, `saagpatel/mcp-trust` | created 2026-06-19 | resolved |
| `fable-outputs` | experimental, medium criticality, active through June 10-22, 2026 Fable window | created 2026-06-19 | resolved for projection; revisit after campaign window |
| `agent-bridge-launch` | no repo, weak catalog contract; launch-material folder for `agent-bridge` | represented by `agent-bridge` Notion row | resolved as `notion_truth_shadow_rows["agent-bridge-launch"] = "agent-bridge"` |
| `PortfolioCommandCenter-public` | archived public/demo mirror of `PortfolioCommandCenter` | exact `PortfolioCommandCenter` Notion row exists | resolved as `notion_truth_shadow_rows["PortfolioCommandCenter-public"] = "PortfolioCommandCenter"` |

## Projection Policy Upgrade

Implemented `notion_projection_policy.v2` with a required
`notion_truth_shadow_rows` map. This map is for truth-side rows that should not
receive their own Local Portfolio Project row because an existing canonical row
already represents them.

Current v2 shadow rows:

- `agent-bridge-launch` -> `agent-bridge`
- `PortfolioCommandCenter-public` -> `PortfolioCommandCenter`

The generated local `output/project-registry.json` policy block was refreshed
from `config/project-registry-overrides.json` after the full portfolio-truth
publish command refused to overwrite the snapshot without Notion context.

## Artifact Refresh

Completed the next strong lane after the projection repair:

- Loaded Notion context from the local Notion repo environment without printing
  the token.
- Refreshed portfolio truth with Notion context intact. The publish guard did
  not fire; the resulting snapshot carries 142 Notion context rows.
- Refreshed the legacy GithubRepoAuditor audit report for all 149 repos.
- Reran `contract-health`; C2 now has no truth-only repos. The remaining
  audit-only repos are a legacy-audit superset difference, not missing truth.
- Repaired portfolio truth remote identity selection so public/canonical
  remotes win over private archive/import origins for the verified local
  mismatch cases. The refreshed truth snapshot was generated at
  `2026-06-19T07:57:10.669963+00:00` and still contains 136 projects.
- Verified the repaired identities:
  - `ApplyKit` now maps to `saagpatel/ApplyKit`.
  - `GithubRepoAuditor` now maps to `saagpatel/GithubRepoAuditor`.
- Reran `contract-health`; latest passing run:
  `2026-06-19T07-57-47Z-59581`.

Current audit-only repos after the June 19 refresh:

- `saagpatel/ApplyKit-private-archive-20260517`
- `saagpatel/GithubRepoAuditor-private-archive-20260518`
- `saagpatel/GithubRepoAuditor-scrubbed-import-20260518`
- `saagpatel/SecondBrain`
- `saagpatel/agent-harness-hardening`
- `saagpatel/ai-workstation-bootstrap`
- `saagpatel/app`
- `saagpatel/claude-code-workstation-bootstrap`
- `saagpatel/codexkit`
- `saagpatel/hermes-agent`
- `saagpatel/personal-ops`
- `saagpatel/portfolio-actuation-sandbox`
- `saagpatel/renovate-config`
- `saagpatel/saagpatel`

## Audit-Only Classification

These rows are present in the refreshed legacy GitHub audit report but absent
from portfolio truth's repo set. They are not all the same kind of drift.

| Audit-only repo | Verified evidence | Classification | Recommended disposition |
| --- | --- | --- | --- |
| `saagpatel/ApplyKit-private-archive-20260517` | Local `/Users/d/Projects/ApplyKit` exists. Local `origin` points to `ApplyKit-private-archive-20260517`; `legacy-origin` points to `ApplyKit`. Portfolio truth now tracks `saagpatel/ApplyKit`, so the remaining audit-only repo is the private archive identity. | private archive mirror | Keep outside portfolio truth. Optional future repo-config cleanup: rename or demote the archive remote so local git configuration is less misleading, but do not create a Local Portfolio Project row. |
| `saagpatel/GithubRepoAuditor-private-archive-20260518` | Local `/Users/d/Projects/GithubRepoAuditor` exists. Local `canonical` points to `GithubRepoAuditor`; `origin` points to `GithubRepoAuditor-private-archive-20260518`. Portfolio truth now tracks `saagpatel/GithubRepoAuditor`, so the remaining audit-only repo is the private archive identity. | private archive mirror | Keep outside portfolio truth. Optional future repo-config cleanup: make the public canonical remote the less surprising local default if approved, but no truth or Notion row action is needed. |
| `saagpatel/GithubRepoAuditor-scrubbed-import-20260518` | No direct local path. Private repo, no explicit catalog entry, same description/topics as GithubRepoAuditor. | import/scrub mirror | Keep outside portfolio truth. Consider upstream archive after confirming it is no longer needed for import provenance. |
| `saagpatel/SecondBrain` | Local path is `/Users/d/Documents/SecondBrain`, outside `/Users/d/Projects`. Project registry already has `supp:SecondBrain` and Notion projection-only treatment. | supplementary non-Projects knowledge vault | Keep outside portfolio truth unless the operator explicitly widens truth beyond `/Users/d/Projects`. Optional future registry cleanup: add repo metadata to supplementary evidence without making it first-class truth. |
| `saagpatel/personal-ops` | Local path is `/Users/d/.local/share/personal-ops`, outside `/Users/d/Projects`. Prior reconciliation explicitly keeps it supplementary unless approved. | supplementary non-Projects control plane | Keep outside portfolio truth without explicit operator approval. It can remain supplementary registry evidence. |
| `saagpatel/codexkit` | Local path is `/Users/d/.codex/codexkit`, outside `/Users/d/Projects`; dirty local operating-layer repo. | supplementary Codex operating surface | Keep outside portfolio truth by default. If promoted later, treat as local operating-system state, not normal product work. |
| `saagpatel/claude-code-workstation-bootstrap` | Local path is `/Users/d/claude-code-workstation-bootstrap`, outside `/Users/d/Projects`; bootstrap branch. | workstation bootstrap/support repo | Keep outside portfolio truth. Archive or mark manual-only upstream if it should stop appearing in legacy audit attention. |
| `saagpatel/portfolio-actuation-sandbox` | Local path is `/Users/d/portfolio-actuation-sandbox`, outside `/Users/d/Projects`; sandbox fixture repo with local dirty files. | actuation sandbox fixture | Keep outside portfolio truth. It is already represented as a Notion projection-only sandbox row, not a portfolio project. |
| `saagpatel/app` | GitHub repo is private and archived; no local direct path. Name collides with existing projection-only Local Portfolio placeholder `app`, but audit description is an archived SwiftUI app. | archived generic app repo | Keep outside portfolio truth. No Local Portfolio row; no action unless upstream archive hygiene is being cleaned. |
| `saagpatel/hermes-agent` | GitHub audit marks it as a fork; no local direct path; no explicit catalog entry. | fork/upstream-derived repo | Keep outside portfolio truth. Archive/delete decision is upstream GitHub hygiene, not portfolio truth work. |
| `saagpatel/agent-harness-hardening` | Public repo, no direct local path, no explicit catalog entry; sanitized hardening artifact. | published support artifact | Keep outside portfolio truth unless it becomes an active infra project with a local operating root. |
| `saagpatel/ai-workstation-bootstrap` | Private repo, no direct local path, no explicit catalog entry; sanitized portable bootstrap. | workstation bootstrap/support repo | Keep outside portfolio truth. Consider archive/manual-only upstream if no longer active. |
| `saagpatel/renovate-config` | Public readme-only shared Renovate config, no direct local path, no explicit catalog entry. | shared config support repo | Keep outside portfolio truth unless dependency-governance work promotes it to active infra. |
| `saagpatel/saagpatel` | Public profile repo, no direct local path, no explicit catalog entry; readme-only profile surface. | GitHub profile repo | Keep outside portfolio truth. Treat as profile/public-presence hygiene, not portfolio project work. |

Net classification after the canonical remote repair:

- First-class truth bug candidates: none currently verified.
- Private archive/import mirrors: `ApplyKit-private-archive-20260517`,
  `GithubRepoAuditor-private-archive-20260518`,
  `GithubRepoAuditor-scrubbed-import-20260518`.
- Supplementary local operating surfaces: `SecondBrain`, `personal-ops`,
  `codexkit`, `claude-code-workstation-bootstrap`,
  `portfolio-actuation-sandbox`.
- Keep-out/default archive/manual-only surfaces: `app`, `hermes-agent`,
  `agent-harness-hardening`, `ai-workstation-bootstrap`, `renovate-config`,
  `saagpatel`.

Do not silently add these 14 repos to portfolio truth. The only high-leverage
repair candidates in this set have now been handled; the rest need an explicit
operator decision before truth scope expands.

## Canonical Remote Repair

Implemented in `src/portfolio_truth_sources.py`:

- Portfolio truth now inspects all configured GitHub fetch remotes instead of
  only `origin`.
- An explicit `canonical` remote wins as the portfolio identity.
- A normal `origin` still wins by default.
- If `origin` looks like a private archive/import identity, a non-archive remote
  whose repo basename matches the local checkout directory can become the
  portfolio identity.

Focused regression tests were added in `tests/test_portfolio_truth.py` for:

- `canonical` beating a private archive `origin`.
- `legacy-origin` public `ApplyKit` beating an archive `origin` when the
  basename matches the checkout.
- normal `origin` behavior staying unchanged.

Verification:

- `uv run ruff check src/portfolio_truth_sources.py tests/test_portfolio_truth.py tests/test_portfolio_truth_sources.py`
- `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_portfolio_truth.py::test_git_remote_full_name_prefers_canonical_remote tests/test_portfolio_truth.py::test_git_remote_full_name_prefers_matching_public_remote_for_archive_origin tests/test_portfolio_truth.py::test_git_remote_full_name_keeps_normal_origin tests/test_portfolio_truth.py::test_extract_github_full_name_uses_exact_github_host tests/test_portfolio_truth.py::test_git_default_branch_reads_local_origin_head tests/test_portfolio_truth.py::test_git_default_branch_keeps_multi_segment_branch tests/test_portfolio_truth.py::test_git_default_branch_empty_when_origin_head_unset -q`
- `PYTHONDONTWRITEBYTECODE=1 uv run pytest tests/test_portfolio_truth.py tests/test_portfolio_truth_sources.py -q`
- `PYTHONDONTWRITEBYTECODE=1 python3 scripts/verify.py --run --id cross-system-smoke:contract-conformance --agent codex`
- `./scripts/run-cross-system-smoke.sh --profile contract-health`

## Mutation Boundary

Safe without live-write approval:

- Refresh local/generated evidence.
- Update repo-local docs or tests.
- Update GithubRepoAuditor projection policy for aliases, projection-only rows,
  and truth-shadow rows already representable by `notion_projection_policy.v2`.

Approval-gated:

- Creating or editing Local Portfolio Project rows in Notion.
- Removing rows from GithubRepoAuditor truth.

## Recommended Next Execution

1. Revisit `fable-outputs` after the June 22, 2026 campaign window and decide
   whether to archive/park upstream.
2. Decide separately whether any supplementary non-Projects surfaces should
   gain repo metadata in project-registry supplementary evidence. Do not promote
   them into first-class truth without explicit approval.
3. If more approved rows are needed later, use the scoped Notion command:

```bash
cd /Users/d/Projects/Notion
npm run portfolio-audit:create-local-project-rows-from-truth -- \
  --today 2026-06-19 \
  --project-title <exact truth display name>
```

Add `--live` only after row-level approval.

## Done Condition

`contract-health` should retain a fresh C7 snapshot and either:

- no longer list active-infra truth-only rows, or
- list only explicitly deferred/projected rows with an approved policy or upstream truth disposition.

Current done state: achieved. `contract-health` passed with no unexpected C7
projection drift.
