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

The operator summary now also answers three questions directly:
- what changed
- why it matters
- what to do next

If you are using watch mode, the tool can now decide full vs incremental per cycle:

```bash
audit <github-username> --watch --watch-strategy adaptive
```

`adaptive` is the default watch strategy. It reuses the stored baseline contract and the full-refresh interval to decide when incremental is still safe and when the next cycle must refresh the full baseline.

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

The same rule now drives adaptive watch mode: if the baseline contract no longer matches or the scheduled full refresh is due, watch escalates to a full run automatically.

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
2. `audit <github-username>` or `audit <github-username> --watch --watch-strategy adaptive`
3. `audit <github-username> --control-center`
4. Read the control-center handoff fields before drilling into the queue, especially the trend summary, primary target, why it is still the top target, what was tried, whether the item is only quieting down or now counts as confirmed resolved, and whether recent confidence has actually been validating
5. Handle `Blocked`, then `Needs Attention Now`, then `Ready for Manual Action`
6. Leave `Safe to Defer` items alone unless priorities changed
7. Run `make workbook-gate` only when workbook-facing changes are part of the release
8. Run `make workbook-signoff ...` after the manual desktop Excel-open check

`--control-center` always writes:

- `output/operator-control-center-<username>-<date>.json`
- `output/operator-control-center-<username>-<date>.md`
- On scheduled runs, the workflow also writes:
  - `output/scheduled-handoff-<username>-<date>.json`
  - `output/scheduled-handoff-<username>-<date>.md`

## Workbook Release Gate

For workbook-facing changes, use:

```bash
make workbook-gate
```

That command generates canonical sample `standard` and `template` workbooks, validates the visible-sheet and hidden `Data_*` invariants, writes an authoritative `workbook-gate-result.json`, produces a readable gate summary, and creates a manual desktop Excel checklist with pending signoff placeholders. The final release step is still opening the generated `standard` workbook in desktop Excel and confirming there is no repair prompt.

After the manual Excel check, record the result back into the local gate artifacts:

```bash
make workbook-signoff ARGS="--reviewer <name> --outcome passed --check excel-open-no-repair=passed --check visible-tabs-present=passed --check normal-zoom-readable=passed --check chart-placement-clean=passed --check filters-work=passed"
```

## Scheduled Issue Automation

Scheduled automation stays artifact-first. A GitHub issue is only opened or updated when the scheduled handoff surfaces meaningful blocked or urgent findings, or when regressions are detected in the diff.

Quiet runs no longer leave the issue hanging open. The workflow now comments with the latest quiet-state handoff, closes the canonical `scheduled-audit-handoff` issue, and reopens that same issue later if a future run becomes noisy again.

The scheduled handoff also now makes the recent direction explicit:

- `worsening`: new blocker/regression pressure appeared or the attention queue grew
- `improving`: attention pressure fell or previously noisy work cleared
- `stable`: the queue is still sticky and needs the same primary target closed next
- `quiet`: the blocked/urgent queue stayed clear long enough to count as a quiet streak

It also now explains the accountability story for the current top target:

- why this item is still the top target
- what would count as done on the next run
- whether the queue is carrying newly stale or chronic follow-through pressure
- what was tried most recently
- whether the latest intervention only quieted the item or produced confirmed resolution evidence

Phase 30 also adds confidence calibration to the same artifact-first story:

- `healthy`: recent high-confidence recommendations have mostly validated
- `mixed`: the guidance is still useful, but recent outcomes stayed partly judgment-heavy
- `noisy`: recent high-confidence guidance has missed often enough that you should verify before overcommitting
- `insufficient-data`: there are not enough judged historical recommendations yet to say whether confidence is earning trust

Phase 31 turns that calibration into live operator guidance:

- `act-now`: the target is high-pressure and the tuned confidence is strong enough to move immediately
- `act-with-review`: the recommendation is strong, but a quick operator review is still healthy
- `verify-first`: the target still matters, but noisy or reopened evidence means you should confirm the latest state before committing
- `monitor`: the queue is calm enough, or the current signal is light enough, that no forceful closure move is justified yet

Phase 32 adds soft trust-policy exceptions and recommendation-drift auditing on top of that:

- soft exceptions can reduce the live trust policy by one step when the same target keeps reopening, underperforming, or flipping between trust policies
- those exceptions stay bounded inside the existing lane buckets; they do not promote lower-priority work above higher-priority work
- `stable`: recent trust-policy behavior is calm enough that no extra caution is needed
- `watch`: the current target has started to wobble between trust policies and deserves a lighter touch
- `drifting`: the current target or recent hotspots have flipped often enough that the recommendation should be treated as less settled

Phase 33 adds one more bounded layer on top of that:

- `useful-caution`: recent softening really was justified because the target stayed unstable, reopened, or remained unresolved
- `overcautious`: recent softening now looks heavier than the evidence supports because the target stabilized cleanly
- `candidate`: the target is stabilizing, but it has not held steady long enough to earn stronger trust
- `earned`: the target has stayed stable long enough that `verify-first` can recover to `act-with-review`
- `blocked`: trust recovery is still blocked by fresh reopen behavior, policy flips, or calibration noise
