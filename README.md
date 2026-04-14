# GitHub Repo Auditor

[![Python](https://img.shields.io/badge/Python-%233776ab?style=flat-square&logo=python)](#) [![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](#) [![Tests](https://img.shields.io/badge/tests-covered-brightgreen?style=flat-square)](#)

> Know the truth about every project you've ever started — because `git log` across 100 repos doesn't tell you which ones are worth finishing.

GitHub Repo Auditor is a portfolio audit and operator tool for developers with a lot of repositories. It clones every repo on your GitHub account, runs 12 analyzers across completeness and interest dimensions, assigns letter grades and achievement badges, preserves historical state, and generates actionable dashboards you can actually use to decide what to work on next. Built for developers who ship fast, start often, and need a system to manage the sprawl.

Today the project is best understood as a GitHub portfolio operating system:

- it tells you which repos are healthy, drifting, blocked, or safe to ignore for now
- it gives you one workbook-first weekly review flow instead of a pile of disconnected reports
- it tracks whether recommended follow-through is actually happening and whether that improvement is holding up over time
- it keeps JSON, Markdown, HTML, workbook, and control-center outputs aligned so you do not have to switch mental models between surfaces

## What This Project Is Today

This project started as a repo auditing tool and has grown into a workbook-first GitHub portfolio operating system.

Today it:

- audits repositories across documentation, testing, CI, dependencies, activity, security, structure, community profile, completeness, and interest signals
- scores repos on dual axes, classifies them into useful tiers, and surfaces quick wins
- generates aligned JSON, Markdown, HTML, workbook, review-pack, and control-center outputs from the same audit facts
- preserves historical state in SQLite so the operator loop can show change, regression, recovery, and follow-through
- keeps the workbook and `--control-center` as the main day-to-day operating surfaces

If you are new here, the simplest way to think about it is: this project tells you which repos are healthy, which ones are drifting, and what to look at next.

## Mode Map

The product now works best when you use one of four explicit modes:

- `First Run` for setup, baseline creation, the first workbook, and the first control-center read
- `Weekly Review` for the normal ongoing operator loop
- `Deep Dive` for repo-level investigation and implementation hotspots
- `Action Sync` for campaigns, writeback, GitHub Projects, and Notion mirroring

The flags stay the same underneath. The modes are the easiest way to understand when to use which workflow.

See [docs/modes.md](/Users/d/Projects/GithubRepoAuditor/docs/modes.md) for the canonical mode guide.

## Recommended Default Path

If you are starting fresh, use this sequence:

```bash
audit <github-username> --doctor
audit <github-username> --html
audit <github-username> --control-center
```

Then open the workbook and read it in this order:

- `Dashboard`
- `Run Changes`
- `Review Queue`
- `Portfolio Explorer`
- `Repo Detail`
- `Executive Summary`

That is the default path the product is optimized around.

## Commands By Mode

### First Run

```bash
audit <github-username> --doctor
audit <github-username> --html
audit <github-username> --control-center
```

### Weekly Review

```bash
audit <github-username> --html
audit <github-username> --control-center
```

### Deep Dive

```bash
audit <github-username> --html --repos <repo-name>
audit <github-username> --control-center
```

### Action Sync

```bash
audit <github-username> --campaign security-review --writeback-target github
audit <github-username> --campaign security-review --writeback-target all --github-projects
audit <github-username> --approval-center
```

Treat campaign/writeback, GitHub Projects, Notion sync, catalog overrides, scorecards overrides, and `--excel-mode template` as advanced paths.

## Demo and Guides

- Demo fixture: [fixtures/demo/sample-report.json](/Users/d/Projects/GithubRepoAuditor/fixtures/demo/sample-report.json)
- Product modes: [docs/modes.md](/Users/d/Projects/GithubRepoAuditor/docs/modes.md)
- Weekly operator workflow: [docs/weekly-review.md](/Users/d/Projects/GithubRepoAuditor/docs/weekly-review.md)
- Operator troubleshooting: [docs/operator-troubleshooting.md](/Users/d/Projects/GithubRepoAuditor/docs/operator-troubleshooting.md)
- Workbook tour: [docs/workbook-tour.md](/Users/d/Projects/GithubRepoAuditor/docs/workbook-tour.md)
- Extending analyzers: [docs/extending-analyzers.md](/Users/d/Projects/GithubRepoAuditor/docs/extending-analyzers.md)

## Features

- **12 Analyzers** — README quality, test coverage, CI/CD, dependency freshness, commit patterns, bus factor, code complexity, security controls, license, build readiness, GraphQL signals, and more
- **Dual-Axis Scoring** — Completeness (does this project have what shipped software should?) and Interest (is this worth anyone's time?) scored independently on 0.0–1.0 scales
- **Letter Grades + Tier Classification** — A–F grades with Shipped / Functional / WIP / Skeleton / Abandoned tiers; 15 achievement badges ("Fully Tested", "CI Champion", "Zero Debt", etc.)
- **Quick Wins Engine** — For each repo, shows exactly which single action moves it to the next tier and how far it is from getting there
- **Multiple Dashboard Outputs** — Flagship Excel workbook with a stable `standard` mode and optional `template` mode, interactive HTML dashboard with scatter chart and tech radar, portfolio README, shields.io badges
- **Workbook-First Operator Review** — Clear reading order through `Dashboard`, `Run Changes`, `Review Queue`, `Portfolio Explorer`, `Repo Detail`, and `Executive Summary`
- **Control Center Queue** — Read-only daily triage that groups work into `Blocked`, `Needs Attention Now`, `Ready for Manual Action`, and `Safe to Defer`
- **Follow-Through Story** — Tracks whether recommendations were untouched, attempted, waiting on evidence, stale, recovering, rebuilding, re-acquired, softening, or retired so the weekly review loop stays honest
- **Repo Drilldowns + Weekly Review Packs** — One-repo briefings and weekly summaries that mirror the same action story across Markdown, HTML, and workbook
- **Notion Integration** — Pushes audit signals into your Notion operating system: completeness cards, managed campaign records, and lifecycle-aware review sync
- **History & Regression Detection** — Archives every run to SQLite, auto-diffs between runs, detects score regressions, and flags archive candidates
- **AI Narrative** — Optional Claude-powered portfolio analysis that reads the audit data and writes a human-readable summary

## Quick Start

### Prerequisites

- Python 3.11+
- A GitHub account (public repos work without a token)
- `GITHUB_TOKEN` env var or `gh` CLI authenticated (for private repos and higher rate limits)

### Installation

```bash
git clone https://github.com/saagpatel/GithubRepoAuditor.git
cd GithubRepoAuditor
python3 -m pip install -e ".[config]"
```

For contributor or local-dev work:

```bash
python3 -m pip install -e ".[dev,config]"
```

### Run

```bash
# Doctor mode — recommended first step
audit <github-username> --doctor

# Weekly Review — generate the native workbook + HTML dashboard
audit <github-username> --html

# Weekly Review — daily read-only triage from the latest state
audit <github-username> --control-center

# Deep Dive — targeted repo rerun merged into the latest baseline
audit <github-username> --repos <repo-name> --html

# Action Sync — managed campaign preview / writeback
audit <github-username> --campaign security-review --writeback-target github
```

Normal runs now perform a lightweight automatic preflight before fetching repos. By default the run stops on blocking errors and continues on warnings. Use `--preflight-mode strict` to fail on warnings too, or `--preflight-mode off` to skip the automatic preflight.

The new `--control-center` path is read-only. It loads the latest report + warehouse state, groups open work into `Blocked`, `Needs Attention Now`, `Ready for Manual Action`, and `Safe to Defer`, and writes `operator-control-center-<username>-<date>.json` plus `.md`.

The new `--approval-center` path is also read-only. It loads the latest report plus approval history, groups work into `Needs Re-Approval`, `Ready For Review`, `Approved But Manual`, and `Blocked`, and writes `approval-center-<username>-<date>.json` plus `.md`. Local approval capture stays separate from writeback apply.

Watch mode now supports `--watch-strategy adaptive|incremental|full`. `adaptive` is the default and uses the stored baseline contract plus the scheduled full-refresh interval to decide whether each watch cycle should run full or incremental.

### Run tests

```bash
pytest
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.11+ |
| GitHub API | REST v3 + GraphQL (raw requests) |
| Excel output | openpyxl + committed workbook template |
| PDF output | fpdf2 |
| AI narrative | Anthropic Claude API |
| Complexity analysis | Radon |
| CLI output | Rich |
| Storage | SQLite (history warehouse) |

## Architecture

The auditor follows a pipeline architecture: fetch repo list via GitHub API → shallow-clone each repo → run all 12 analyzers in sequence → aggregate scores → generate outputs. Analyzers are pluggable via `--analyzers-dir` for custom extensions. The scoring engine computes completeness and interest independently, applies configurable scoring profiles, and derives letter grades from the combined result. All output writers (Excel, HTML, JSON, Markdown, Notion) are isolated from the analysis layer and consume the same scored result object. Workbook ranking and trend views always use the full filtered portfolio baseline, even for targeted or incremental reruns.

Partial reruns now require a compatible full-baseline report, not just any previous report. The stored baseline contract tracks the audit-affecting portfolio context used to produce the last trustworthy baseline, and targeted or incremental reruns will fail closed if that contract no longer matches the current request.

Before normal runs start, the CLI now performs a shared preflight that checks config validity, token/config readiness for requested integrations, template/workbook availability, output writability, and whether targeted or incremental paths have a usable baseline. `--doctor` runs the broader diagnostics set without auditing repos and writes a machine-readable JSON artifact to `output/diagnostics-<username>-<date>.json`.

For day-to-day operations, `--control-center` is now the clean read-only entrypoint. It reuses the latest report, review state, campaign history, governance drift, and setup health to build one shared operator queue without running a new audit or mutating any external system.

Watch mode now uses that same baseline contract in live execution. Each cycle records the requested watch strategy, the chosen mode, and the reason a full refresh was required or an incremental rerun remained safe.

`pyproject.toml` is the canonical dependency definition, and `requirements.txt` is kept as a synchronized compatibility mirror for environments that still prefer a flat requirements file.

## Excel Workbook

The workbook now supports two modes:

- `--excel-mode standard` — stable operational workbook path, the CLI default, and the recommended mode for automation and Mac Excel compatibility
- `--excel-mode template` — template-backed workbook path using `assets/excel/analyst-template.xlsx` for controlled template work

Both modes read from the same report + warehouse facts. Python owns the hidden `Data_*` sheets, stable table names, and workbook facts. The template-backed workbook still owns the template shell, named-range bindings, native sparkline placement, and print layout, but the standard workbook path is now the safest default for automated generation and Excel compatibility.

Template mode is also validated during preflight: the committed workbook asset must exist and pass a lightweight shell check before the run will continue.

This workbook boundary is unchanged in the current phase: the project still emits one workbook artifact, visible sheets remain filter-based, and hidden `Data_*` sheets remain the contract surface for workbook facts and downstream bindings.

The workbook’s main visible flow is now:
- `Index` for orientation
- `Dashboard` for the big-picture read
- `Run Changes` for what moved this run
- `Review Queue` for action
- `Portfolio Explorer` for comparison
- `Repo Detail` for one-repo drilldown
- `Executive Summary` for a one-page shareable readout

For workbook-facing changes, use the canonical release gate:

```bash
make workbook-gate
```

That command generates stable sample `standard` and `template` workbooks, validates the visible-sheet and hidden `Data_*` invariants, writes an authoritative `workbook-gate-result.json`, adds a human-readable gate summary, and produces a manual desktop Excel checklist. The final release step is still opening the generated `standard` workbook in desktop Excel and recording the local signoff outcome with `make workbook-signoff`.

After that manual desktop Excel check, record the outcome back into the gate artifacts:

```bash
make workbook-signoff ARGS="--reviewer <name> --outcome passed --check excel-open-no-repair=passed --check visible-tabs-present=passed --check normal-zoom-readable=passed --check chart-placement-clean=passed --check filters-work=passed"
```

## Managed Campaigns and Governance

Campaign writeback is now lifecycle-aware rather than one-shot:

- `--campaign-sync-mode reconcile` updates active managed records and closes stale ones
- `--campaign-sync-mode append-only` leaves stale managed records open and marks them stale
- `--campaign-sync-mode close-missing` aggressively closes previously managed records that no longer belong in the campaign

Managed state drift, rollback coverage, and campaign history are written into JSON, Markdown, HTML, Excel, and the warehouse snapshot. Governed security controls still remain manual and opt-in, but operator surfaces now distinguish ready, approved, applied, drifted, and rollback coverage states when governance data is present.

When writeback or governance-related actions are requested, preflight checks now validate the required GitHub and Notion prerequisites before any external mutation path starts.

## Operator Loop

The daily operator loop is now:

- Run `audit <github-username> --doctor`
- Run `audit <github-username>` or `audit <github-username> --watch --watch-strategy adaptive`
- Run `audit <github-username> --control-center`
- Review the handoff fields: what changed, why it matters, what to do next, whether the queue is improving or worsening, what was tried for the top target, whether it is only quieting down or now counts as confirmed resolved, and whether recent confidence has actually been validating
- Open the workbook and review it in this order: `Dashboard`, `Run Changes`, `Review Queue`, `Portfolio Explorer`, `Repo Detail`, `Executive Summary`
- Clear anything in `Blocked` first
- Use the reported primary target as the single next thing to close before taking on newly ready work
- Review `Needs Attention Now` for drift and high-severity changes
- Work through `Ready for Manual Action`
- Leave `Safe to Defer` items alone unless priorities change
- Run `make workbook-gate` only when workbook-facing changes are in scope
- Run `make workbook-signoff ...` after the manual Excel-open check for workbook-facing changes

Scheduled automation stays artifact-first. The weekly workflow now runs the audit, generates a control-center artifact plus a scheduled handoff summary, uploads `output/`, opens or updates one canonical GitHub issue only when blocked or urgent operator findings cross a meaningful threshold, and closes that same issue cleanly when later runs return to a quiet state. The handoff now also calls out whether the queue is getting better, worse, or staying stuck, what was tried most recently, whether that intervention actually helped, whether recovery is only quiet for now or confirmed resolved, whether recent high-confidence guidance has been validating or turning noisy, what trust policy now applies to the live recommendation (`act-now`, `act-with-review`, `verify-first`, or `monitor`), whether a soft exception or recent policy-flip drift should make the operator treat that recommendation more cautiously, and whether recent soft caution is still earning trust or has become cautious enough to recover toward a stronger policy.

In newer follow-through phases, that same weekly story also carries whether a recommendation is escalating, recovering, rebuilding, re-acquiring confidence, or aging back down. The important product principle is still the same: workbook, HTML, Markdown, and review-pack surfaces should tell the same story in different formats.

## Troubleshooting

The fastest path for setup issues is:

```bash
audit <github-username> --doctor
```

Common fixes:

- Missing GitHub token: set `GITHUB_TOKEN` or pass `--token` for private-repo access, GitHub writeback, metadata apply flows, and other authenticated actions.
- Missing or broken Notion config: create or fix `config/notion-config.json` before using `--notion-sync`, `--notion-registry`, or Notion writeback.
- Starting from scratch: copy `config/examples/audit-config.example.yaml` to `audit-config.yaml` and `config/examples/notion-config.example.json` to `config/notion-config.json`.
- Missing Excel template: restore `assets/excel/analyst-template.xlsx` or use `--excel-mode standard`.
- Missing baseline report: run a full audit before using `--repos`, `--incremental`, or other baseline-dependent workflows.
- Config/profile errors: fix `audit-config.yaml` syntax or choose an existing scoring profile under `config/scoring-profiles/`.

There is also a longer operator guide in [docs/operator-troubleshooting.md](docs/operator-troubleshooting.md).

## License

MIT
