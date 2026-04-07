# Operator Troubleshooting

Start here when a run fails before auditing:

```bash
audit <github-username> --doctor
```

That command checks the same shared setup prerequisites the normal preflight uses, but it does not fetch repos, clone anything, or push to external systems.

For the day-to-day operator loop, use:

```bash
audit <github-username> --control-center
```

That command is read-only. It loads the latest report + warehouse state, groups triage items into `Blocked`, `Needs Attention Now`, `Ready for Manual Action`, and `Safe to Defer`, and writes matching JSON + Markdown control-center artifacts.

## Common Issues

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

### Missing scoring profile

Symptoms:
- requested scoring profile was not found

Fix:
- choose an existing profile under `config/scoring-profiles/`
- or remove `--scoring-profile`

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

Common required fields:
- `events_database_id` for `--notion-sync`
- `projects_data_source_id` for `--notion-registry`
- `action_requests_*` and `campaign_runs_*` or `recommendation_runs_*` for Notion writeback

### Missing Excel template

Symptoms:
- template-mode preflight failure

Fix:
- restore `assets/excel/analyst-template.xlsx`
- or run with `--excel-mode standard`

Standard mode is the stable operational workbook path, the default workbook mode, and the safest choice for Mac Excel compatibility. Template mode remains available when template-specific layout work is needed.

### Missing baseline report for targeted or incremental runs

Symptoms:
- blocking preflight error before `--repos`
- blocking preflight error before `--incremental`

Fix:
- run a full audit first

Targeted and incremental reruns depend on the full filtered portfolio baseline, both for merging outputs and for keeping interest/novelty scoring stable.

### Missing incremental fingerprints

Symptoms:
- incremental mode reports that saved fingerprints are missing

Fix:
- run a full audit first so the tool can seed `.audit-fingerprints.json` in the chosen output directory

## Preflight Modes

- `--preflight-mode auto`: default; fail on errors, continue on warnings
- `--preflight-mode strict`: fail on warnings too
- `--preflight-mode off`: skip automatic preflight on normal runs

`--doctor` always writes a diagnostics artifact to `output/diagnostics-<username>-<date>.json`.

## Daily Loop

The intended operator loop is:

1. `audit <github-username> --doctor`
2. `audit <github-username>`
3. `audit <github-username> --control-center`
4. Handle `Blocked`, then `Needs Attention Now`, then `Ready for Manual Action`
5. Leave `Safe to Defer` items alone unless priorities changed

`--control-center` always writes:

- `output/operator-control-center-<username>-<date>.json`
- `output/operator-control-center-<username>-<date>.md`
