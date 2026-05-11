# CLI Migration: flat form → subcommand form

Arc F Sprint 4.3 introduced four subcommands — `run`, `triage`, `report`, and `serve` —
to replace the flat `audit <username> --flag` invocation style. The flat form still
works and emits a deprecation warning; it will not be removed until a future major
version bump.

## Why the change

The flat CLI accumulated more than 70 flags over the project's lifetime. Grouping them
into subcommands makes the tool more discoverable (`audit run --help` shows only
audit-run flags) and makes it clearer which flags belong to which workflow.

The mapping is:

| Subcommand | Purpose |
|------------|---------|
| `audit run` | Fetch, clone, analyze, and score repos (the main audit cycle) |
| `audit triage` | Control-center, approval queues, acknowledgments, semantic search |
| `audit report` | Portfolio truth, Excel workbooks, campaigns, writeback, exports |
| `audit serve` | Local FastAPI + HTMX web UI |

## Flag family mapping

### audit run

Flags that belong here: `--repos`, `--skip-forks`, `--skip-archived`, `--skip-clone`,
`--incremental`, `--graphql`, `--badges`, `--html`, `--pdf`, `--narrative`,
`--briefing`, `--fetch-mode`, `--analysis-workers`, `--no-cache`,
`--scoring-profile`, `--watch`, `--resume`, `--vuln-check`, `--reindex`,
`--embedder`.

Global flags available in all subcommands: `--token`, `--output-dir`, `--config`,
`--verbose`.

### audit triage

Flags that belong here: `--control-center`, `--approval-center`, `--triage-view`,
`--approval-view`, `--auto-apply-approved`, `--dry-run`, `--approve-governance`,
`--approve-packet`, `--review-governance`, `--review-packet`, `--reset-prefs`,
`--acknowledge-target`, `--acknowledge-kind`, `--semantic-search`, `--ask`.

### audit report

Flags that belong here: `--portfolio-truth`, `--portfolio-context-recovery`,
`--apply-context-recovery`, `--excel-mode`, `--diff`, `--summary`, `--scorecard`,
`--campaign`, `--writeback-target`, `--writeback-apply`, `--github-projects`,
`--campaign-sync-mode`, `--max-actions`, `--apply-metadata`, `--apply-readmes`,
`--improvements-file`, `--generate-manifest`, `--create-issues`, `--upload-badges`,
`--notion-sync`, `--notion-registry`, `--portfolio-profile`, `--collection`.

### audit serve

Flags that belong here: `--port`, `--host`. Plus the shared globals above.

## Before → after examples

The eight most common invocations:

| Before (flat, deprecated) | After (subcommand) |
|---------------------------|--------------------|
| `audit <user> --doctor` | `audit run <user> --doctor` (or keep flat — `--doctor` still works) |
| `audit <user> --html` | `audit run <user> --html` |
| `audit <user> --control-center` | `audit triage <user> --control-center` |
| `audit <user> --portfolio-truth` | `audit report <user> --portfolio-truth` |
| `audit <user> --repos my-repo --html` | `audit run <user> --repos my-repo --html` |
| `audit <user> --briefing` | `audit run <user> --briefing` |
| `audit <user> --campaign security-review --writeback-target github` | `audit report <user> --campaign security-review --writeback-target github` |
| `audit <user> --semantic-search "Python projects"` | `audit triage <user> --semantic-search "Python projects"` |

## Daily flow in subcommand form

```bash
# 1. Run the audit
audit run <username> --html

# 2. Review operator state
audit triage <username> --control-center

# 3. Refresh portfolio truth
audit report <username> --portfolio-truth

# 4. Browse results in the browser
audit serve
```

## Deprecation warning

When you invoke the flat form, the CLI prints a one-time deprecation warning to stderr:

```
DeprecationWarning: Flat invocation is deprecated. Use subcommand form:
  audit run <username> [flags]
See: docs/audit-cli-migration.md
```

The warning fires at most once per process. It is informational — the run proceeds
normally. Flat form is not scheduled for removal; it will remain until a deliberate
major-version bump with a migration window.

## Advanced flags

A small number of advanced flags (e.g. `--watch-interval`, `--preflight-mode`,
`--allow-dirty-worktree`, `--workspace-root`) are not surfaced in the subcommand help
to keep the per-subcommand flag list short. They are still accepted when passed via
the flat form or when passed after the subcommand (the underlying parser accepts all
flags). Run `audit <username> --help` for the full flat-form flag reference.
