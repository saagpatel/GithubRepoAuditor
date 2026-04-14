# Operator Troubleshooting

Use this guide when the workflow is failing or a required artifact is missing. For the normal weekly loop, use [weekly-review.md](/Users/d/Projects/GithubRepoAuditor/docs/weekly-review.md). For the high-level product map, use [modes.md](/Users/d/Projects/GithubRepoAuditor/docs/modes.md).

Start here first:

```bash
audit <github-username> --doctor
```

That checks the same shared setup and baseline prerequisites the normal preflight uses, but it does not fetch repos, clone anything, or push to external systems.

## Common issues

### Missing GitHub token

Symptoms:
- public-repo-only warning during normal runs
- blocking error before GitHub writeback, metadata apply, or README apply workflows

Fix:
- set `GITHUB_TOKEN`
- or pass `--token`

Use a token whenever you need private-repo access, higher rate limits, or any GitHub mutation path.

### Missing or broken `audit-config.yaml`

Symptoms:
- config parse error
- unknown config key warning
- unsupported value warning/error

Fix:
- repair YAML syntax
- make sure the file root is a mapping of option names to values
- use only supported option values such as `--excel-mode template|standard`

### Missing scoring profile, catalog, or scorecards config

Symptoms:
- requested scoring profile was not found
- catalog path warning
- scorecards path warning

Fix:
- choose an existing profile under `config/scoring-profiles/`
- repair the configured file path
- or remove the optional override

Missing catalog or scorecards files should not break a normal audit, but they can reduce the richness of the visible operator story.

### Missing Notion token or config

Symptoms:
- blocking error before `--notion-sync`
- blocking error before `--notion-registry`
- blocking error before Notion writeback

Fix:
- set `NOTION_TOKEN`
- create or repair `config/notion-config.json`
- start from `config/examples/notion-config.example.json` if you need a working template
- make sure the required database or data-source IDs are present for the feature you requested

### Missing GitHub Projects config

Symptoms:
- GitHub Projects mirroring is skipped
- campaign preview says GitHub Projects config is missing or invalid

Fix:
- create or repair `config/github-projects.yaml`
- or pass `--github-projects-config PATH`

Projects mirroring is optional and preview-first. It should not block the normal audit workflow.

### Missing Excel template

Symptoms:
- template-mode preflight failure

Fix:
- restore `assets/excel/analyst-template.xlsx`
- or run with `--excel-mode standard`

`standard` mode is the default and recommended workbook path.

### Missing baseline report for targeted or incremental runs

Symptoms:
- blocking preflight error before `--repos`
- blocking preflight error before `--incremental`

Fix:
- run a full audit first

Targeted and incremental reruns depend on the full filtered portfolio baseline, both for merged outputs and for stable portfolio comparisons.

### Missing incremental fingerprints

Symptoms:
- incremental mode reports that saved fingerprints are missing

Fix:
- run a full audit first so the tool can seed `.audit-fingerprints.json` in the chosen output directory

### Missing latest report for `--control-center`

Symptoms:
- `--control-center` fails because no report exists yet

Fix:
- run a normal audit first
- then rerun `audit <github-username> --control-center`

The control center is read-only and depends on the latest stored report plus warehouse history.

## Preflight modes

- `--preflight-mode auto`: default; fail on errors, continue on warnings
- `--preflight-mode strict`: fail on warnings too
- `--preflight-mode off`: skip automatic preflight on normal runs

`--doctor` always writes a diagnostics artifact to `output/diagnostics-<username>-<date>.json`.

## Workbook release gate

For workbook-facing code changes, use:

```bash
make workbook-gate
```

That command generates canonical sample `standard` and `template` workbooks, validates visible-sheet and hidden `Data_*` invariants, writes `workbook-gate-result.json`, and creates the manual desktop Excel checklist.

After the manual Excel-open check, record the signoff:

```bash
make workbook-signoff ARGS="--reviewer <name> --outcome passed --check excel-open-no-repair=passed --check visible-tabs-present=passed --check normal-zoom-readable=passed --check chart-placement-clean=passed --check filters-work=passed"
```

## Scheduled handoff issues

Scheduled automation is artifact-first. A GitHub issue is only opened or updated when the scheduled handoff surfaces meaningful blocked or urgent findings, or when regressions appear in the diff.

If scheduled output looks wrong:
- confirm the latest audit and control-center artifacts exist in `output/`
- confirm the latest report is newer than any stale handoff artifact
- confirm queue pressure actually changed before expecting a new noisy issue

Quiet runs can close the canonical scheduled handoff issue after writing the quiet-state artifact. That is expected behavior now, not a failure.

## Automation guidance cues

If the product surfaces `Automation Guidance`, treat it as a safety posture, not an auto-run signal.

- `preview-safe` means the surfaced preview command is a safe planning step
- `apply-manual` means the command is still human-only even if it is shown
- `approval-first` and `manual-only` mean review work should happen before execution
- `follow-up-safe` means only non-mutating refresh or monitoring is appropriate

If the wording ever implies that `--writeback-apply` will run automatically, treat that as a bug and fall back to the workbook plus control-center review path.
