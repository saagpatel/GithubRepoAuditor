# AGENTS.md

## What This Project Is

`GithubRepoAuditor` is the workbook-first portfolio operating system for repo truth and weekly review. It generates the canonical local portfolio truth snapshot consumed by downstream dashboards, reports, command-center surfaces, and planning lanes.

## Current State

The current machine-readable truth surface is `output/portfolio-truth-latest.json`. Compatibility Markdown, workbooks, dashboards, and reports are derived surfaces; do not treat them as canonical inputs unless a task is specifically about that artifact.

## Stack

- Python
- `uv`
- pytest
- ruff
- Local JSON, Markdown, HTML, workbook, and control-center outputs

## How To Run

Refresh and verify the local portfolio truth snapshot:

```sh
uv run python -m src.cli report saagpatel --portfolio-truth
jq '{generated_at,total:(.projects|length),counts:.source_summary.attention_state_counts}' output/portfolio-truth-latest.json
uv run operator-os-seam-linter --truth output/portfolio-truth-latest.json --json
```

Useful checks for repo changes:

```sh
uv run ruff check .
uv run pytest -q
```

Use narrower tests when the change is scoped and the full suite would be disproportionate.

The seam-linter checks truth freshness, schema pinning, and generated Markdown
provenance markers. Its identity-resolution check is opt-in:

```sh
uv run operator-os-seam-linter --identity-resolution --identity-since 2026-07-03T13:02:06Z --truth output/portfolio-truth-latest.json --json
```

Use `--identity-since` for regression-gate checks after producer fixes. It
filters timestamped local stores only: bridge-db activity, session-costs, and
notification-hub durable events. Untimestamped Notion snapshot rows are skipped
in since-window mode.

## Known Risks

- `output/portfolio-truth-latest.json` is generated state, but it is also the current truth surface for other local workflows. Regenerate it deliberately after catalog or context changes.
- Do not let generated reports, old dashboards, or historical registry files override the latest portfolio truth snapshot.
- Do not read or emit secrets, `.env` values, keychains, OAuth stores, raw private transcripts, raw logs, browser profiles, or credential-bearing configs while auditing repos.

## Next Recommended Move

When repairing portfolio context, keep the attention contract tight: improve default-attention repos only when the work supports a real publish, park, archive, security, release, dirty-worktree, owner, active-product, bridge/Notion/sync, or cost decision.
