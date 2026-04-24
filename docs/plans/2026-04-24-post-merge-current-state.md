# Post-Merge Current State - 2026-04-24

## Status

PR #120, PR #121, and PR #122 are merged into `main`.

- PR #120 closed the workbook/export and operator-trend refactor batch, stabilized time-sensitive tests, and refreshed stale operator docs.
- PR #121 updated GitHub Actions to Node 24-compatible major versions.
- PR #122 recorded the post-merge rehearsal state and restored `python3 -m src.cli --help` behavior.
- Latest verified local branch before this note update: `main` aligned with `origin/main` at merge commit `743d833`.
- Latest verified GitHub main CI after PR #122: passed.

No P1/P2/P3 review findings from the April repair list remain open.

## Rehearsal Results

Live weekly rehearsal was run from current `main` with the repo-native CLI entrypoint:

```bash
python3 -m src saagpatel --doctor
python3 -m src saagpatel --html --review-pack --badges --excel-mode standard
python3 -m src saagpatel --control-center
make workbook-gate
python3 -m src saagpatel --portfolio-truth --registry-output output/project-registry.md --portfolio-report-output output/PORTFOLIO-AUDIT-REPORT.md
python3 -m src saagpatel --approval-center
python3 -m src saagpatel --auto-apply-approved --dry-run
```

Observed results:

- Doctor completed with no blocking errors.
- Doctor warnings were expected optional-environment gaps: no `audit-config.yaml`, no `NOTION_TOKEN`, and no `config/notion-config.json`.
- Full audit completed against 114 GitHub repos.
- Fresh artifacts were generated for `2026-04-24`, including audit report, workbook, HTML dashboard, badges, review pack, control center, weekly command center, approval center, and portfolio truth.
- Audit score summary: average score `0.708`; tiers reported as `60 functional`, `44 shipped`, `7 wip`, and `3 skeleton`.
- Control center state is urgent/sticky, led by `AIGCCore shifted on momentum`.
- Workbook gate automated checks passed; manual desktop Excel signoff remains pending for this rehearsal.
- Portfolio truth generated for 115 projects.
- Approval center reported no current approval needs review.
- Auto-apply dry run reported no `approved-manual` campaign packets.

## Current Gates

Phase 123 is not ready for live automated apply.

Reasons:

- Portfolio truth currently has `0` automation-eligible projects.
- Approval center has no current approval needing review.
- Auto-apply dry run found no approved-manual campaign packets.

The safe next Phase 123 preparation is to choose 2-3 low-risk candidate repos, make their catalog/truth state explicitly automation-eligible, approve a bounded campaign packet, then rerun the dry-run gate before any live apply.

## Maintenance Findings

The post-refactor helper split is green but now has visible sprawl:

- `src/operator_trend*.py`: 30 files, about 15,217 lines.
- `src/excel*.py`: 49 files, about 15,440 lines including `src/excel_export.py`.
- The longest operator-trend module names are near 100 characters and encode too many lifecycle states in filenames.

Recommended maintainability pass:

1. Group `operator_trend_closure_forecast_*` helpers behind 3-5 conceptual modules instead of many recursively named stages.
2. Keep compatibility imports stable while consolidating names.
3. Preserve the scoped mypy command in `.github/workflows/ci.yml` during the consolidation.
4. Verify with full pytest, Ruff, scoped mypy, `python3 -m src --help`, `python3 -m src.cli --help`, and `make workbook-gate`.

## Follow-Ups

1. Complete manual desktop Excel signoff for the generated workbook if this rehearsal becomes a release record.
2. Reduce GitHub security endpoint warning noise; expected 403/404 responses from code/secret-scanning alert endpoints should be summarized or quieted without hiding real API outages.
3. Use `python3 -m src` or the installed `audit` console script after `pip install -e ".[dev,config]"`; PR #122 restored `python3 -m src.cli --help` behavior.
4. Start Phase 123 only after explicit catalog eligibility and approval-center readiness exist.
