# Phase 103 Closeout

## Review Of What Was Built

Phase 103 shipped a dedicated portfolio truth subsystem instead of extending the weekly/report pipeline.

Core delivered behavior:
- added a versioned canonical truth contract in [`src/portfolio_truth_types.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_truth_types.py)
- added safe workspace, legacy-registry, and optional Notion source adapters in [`src/portfolio_truth_sources.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_truth_sources.py)
- added field-by-field reconciliation and provenance in [`src/portfolio_truth_reconcile.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_truth_reconcile.py)
- added truth/output validation and publish safety checks in [`src/portfolio_truth_validate.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_truth_validate.py) and [`src/portfolio_truth_publish.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_truth_publish.py)
- added compatibility renderers for the shared workspace artifacts in [`src/portfolio_truth_render.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_truth_render.py)
- added the CLI entrypoint `audit <github-username> --portfolio-truth` in [`src/cli.py`](/Users/d/Projects/GithubRepoAuditor/src/cli.py)
- extended [`config/portfolio-catalog.yaml`](/Users/d/Projects/GithubRepoAuditor/config/portfolio-catalog.yaml) and [`src/portfolio_catalog.py`](/Users/d/Projects/GithubRepoAuditor/src/portfolio_catalog.py) so grouped-folder defaults can be declared instead of inferred

Compatibility and publish behavior that now exists:
- the canonical machine-readable artifact is now [`output/portfolio-truth-latest.json`](/Users/d/Projects/GithubRepoAuditor/output/portfolio-truth-latest.json)
- dated historical truth snapshots are written alongside it in `output/`
- `/Users/d/Projects/project-registry.md` is now generated from the truth snapshot
- `/Users/d/Projects/PORTFOLIO-AUDIT-REPORT.md` is now generated from the same truth snapshot and explicitly framed as derived, not canonical
- publish is staged through temp files and replace-on-success behavior
- unchanged compatibility outputs are not rewritten
- `--sync-registry` now fails closed instead of silently mutating the shared registry

The live publish pass succeeded against the real workspace after the validation pass was hardened for two real portfolio conditions:
- a duplicate display name (`OrbitForge`) still exists across compatibility sections
- one project path still carries leading whitespace in the underlying folder name (`Fun:GamePrjs/ CryptForge`)

The generated live snapshot currently reports:
- `113` discovered projects
- `59` active
- `18` recent
- `21` parked
- `15` archived
- duplicate display name warning for `OrbitForge`

## Cleanup Review

Removed or shut down:
- the old `--sync-registry` mutation path is no longer allowed
- the brittle live-home-path registry parser assertion in [`tests/test_registry_parser.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_registry_parser.py) was replaced with a hermetic compatibility fixture

Simplified or contained:
- portfolio truth generation no longer rides inside `AuditReport`
- workspace compatibility publishing is isolated behind one publish module instead of scattered `write_text()` calls
- grouped-folder policy now has a declared config seam instead of living only in code assumptions

Temporary compatibility shims that remain:
- `project-registry.md` is still a lossy compatibility surface keyed by display name, so duplicate names still collapse in parser-style consumers
- the legacy registry still feeds migration evidence for category/tool/notes where explicit catalog data is missing
- root-level Swift projects still depend on a bounded compatibility inference to stay visible under the iOS section

Open cleanup findings that should not be forgotten:
- `OrbitForge` still exists as a duplicate display name across two compatibility sections
- `Fun:GamePrjs/ CryptForge` still exposes a leading-space path in the live workspace
- many projects still fall back to `unknown` category or tool because explicit catalog contracts are missing
- Notion context remains optional and currently contributed `0` rows on the live publish

Automation-noise and secrets-exposure posture:
- compatibility outputs now skip rewrites when content is unchanged, which reduces false automation churn for the active weekly portfolio review automation
- the truth layer only reads small allowlisted text/manifests, refuses symlinks, and does not persist raw Notion `next_move` text
- the durable truth artifact still includes the absolute workspace root at the snapshot top level; that is acceptable for this local-first system today but should remain intentional

## Verification Summary

Focused local verification run:
- `python3 -m ruff check src tests`
- `pytest -q tests/test_portfolio_truth.py tests/test_portfolio_catalog.py tests/test_registry_parser.py tests/test_notion_registry.py`

What those checks covered:
- truth contract and precedence behavior
- grouped-folder catalog rules
- registry parser compatibility
- no-op publish behavior
- publish-failure safety
- CLI override path behavior
- fail-closed `--sync-registry`

Live workspace verification:
- ran `audit d --portfolio-truth` through the CLI entrypoint
- regenerated `/Users/d/Projects/project-registry.md`
- regenerated `/Users/d/Projects/PORTFOLIO-AUDIT-REPORT.md`
- wrote [`output/portfolio-truth-latest.json`](/Users/d/Projects/GithubRepoAuditor/output/portfolio-truth-latest.json) plus a dated snapshot

Not run in this phase:
- workbook-facing gates, because the workbook/report pipeline was intentionally not changed
- broad `pytest -q`, because the truth-layer cut was isolated and the targeted suite already covered the touched seams directly

## Shipped Summary

`GithubRepoAuditor` now owns a real portfolio truth layer for `/Users/d/Projects`.

After Phase 103:
- one canonical truth snapshot exists
- the shared registry and portfolio audit report are generated from that truth snapshot
- the old direct registry mutation seam is closed
- grouped-folder defaults have a declared config home
- the system can publish compatibility outputs safely without forcing unnecessary file churn

This phase did **not** solve context quality yet. It made the truth and compatibility layer real enough that Phase 104 can improve context on top of stable portfolio facts instead of stale markdown.

## Next Phase

### Phase 104: Minimum Viable Context Recovery

The next phase should improve context quality for active and recent projects first, using the new truth layer as the authoritative project inventory.

Immediate starting point:
1. read [`output/portfolio-truth-latest.json`](/Users/d/Projects/GithubRepoAuditor/output/portfolio-truth-latest.json) as the canonical project inventory
2. target projects whose `registry_status` is `active` or `recent` and whose `context_quality` is `none` or `boilerplate`
3. define the new context-quality ladder:
   - `none`
   - `boilerplate`
   - `minimum-viable`
   - `standard`
   - `full`
4. decide which minimum files and fields make a project “minimum-viable”, at minimum:
   - what the project is
   - current state
   - stack
   - how to run it
   - known risks
   - next recommended move
5. make the truth layer understand the new `minimum-viable` band without weakening the stricter `standard` and `full` bands
6. build a repeatable context-recovery workflow that can update one project at a time without inventing a second source of truth

Execution guidance for Phase 104:
- start with the live truth snapshot counts and sort candidates by `active/recent` plus weak context
- treat grouped boilerplate-heavy sections as batch candidates only after the highest-signal standalone projects are addressed
- keep context recovery local and report-first; do not mix it with automation restart
- preserve the strict scan contract from Phase 103 so context detection stays safe and predictable
- add tests that prove the truth layer can distinguish `minimum-viable` from `boilerplate`

Known Phase 104 risks already exposed by Phase 103:
- duplicate display names will make context-recovery reporting noisier if they are not handled explicitly
- some current “standard” classifications are still optimistic because they rely on shallow AGENTS/CLAUDE presence rather than a richer semantic contract
- catalog coverage is still weak, so context recovery and declared portfolio intent will continue to drift unless repo/group contracts are filled in alongside context work

## Remaining Roadmap

- `Phase 105` — Turn trust/effectiveness signals into a measurable decision-quality layer for weekly recommendations and future automation gates.
- `Phase 106` — Introduce explicit portfolio golden paths like maintain, finish, archive, and experiment so weekly guidance becomes intent-aware instead of generic.
- `Phase 107` — Reboot a bounded weekly command-center automation loop only after truth, context, and decision-quality inputs are strong enough.
- `Phase 108` — Add a structured risk overlay and a reusable doctor/release standard across the key repos in the workspace.
