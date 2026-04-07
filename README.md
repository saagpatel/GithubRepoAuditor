# GitHub Repo Auditor

[![Python](https://img.shields.io/badge/Python-%233776ab?style=flat-square&logo=python)](#) [![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](#) [![Tests](https://img.shields.io/badge/tests-covered-brightgreen?style=flat-square)](#)

> Know the truth about every project you've ever started — because `git log` across 100 repos doesn't tell you which ones are worth finishing.

GitHub Repo Auditor clones every repo on your GitHub account, runs 12 analyzers across completeness and interest dimensions, assigns letter grades and achievement badges, and generates actionable dashboards you can actually use to decide what to work on next. Built for developers who ship fast, start often, and need a system to manage the sprawl.

## Features

- **12 Analyzers** — README quality, test coverage, CI/CD, dependency freshness, commit patterns, bus factor, code complexity, security controls, license, build readiness, GraphQL signals, and more
- **Dual-Axis Scoring** — Completeness (does this project have what shipped software should?) and Interest (is this worth anyone's time?) scored independently on 0.0–1.0 scales
- **Letter Grades + Tier Classification** — A–F grades with Shipped / Functional / WIP / Skeleton / Abandoned tiers; 15 achievement badges ("Fully Tested", "CI Champion", "Zero Debt", etc.)
- **Quick Wins Engine** — For each repo, shows exactly which single action moves it to the next tier and how far it is from getting there
- **Multiple Dashboard Outputs** — Flagship Excel workbook with `template` and `standard` modes, interactive HTML dashboard with scatter chart and tech radar, portfolio README, shields.io badges
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
# Doctor mode — validate setup before auditing
audit <github-username> --doctor

# Control center — daily read-only triage from the latest state
audit <github-username> --control-center

# Audit a GitHub user's repos
audit <github-username>

# Generate the native workbook + HTML dashboard
audit <github-username> --html --excel-mode template

# Dry run — no cloning, no writes
audit <github-username> --dry-run

# Supported fallback if you prefer module execution
python -m src <github-username> --doctor
```

Normal runs now perform a lightweight automatic preflight before fetching repos. By default the run stops on blocking errors and continues on warnings. Use `--preflight-mode strict` to fail on warnings too, or `--preflight-mode off` to skip the automatic preflight.

The new `--control-center` path is read-only. It loads the latest report + warehouse state, groups open work into `Blocked`, `Needs Attention Now`, `Ready for Manual Action`, and `Safe to Defer`, and writes `operator-control-center-<username>-<date>.json` plus `.md`.

### First-Run Flow

```bash
make install
cp .env.example .env
cp config/examples/audit-config.example.yaml audit-config.yaml
audit <github-username> --doctor
audit <github-username>
audit <github-username> --control-center
```

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

Before normal runs start, the CLI now performs a shared preflight that checks config validity, token/config readiness for requested integrations, template/workbook availability, output writability, and whether targeted or incremental paths have a usable baseline. `--doctor` runs the broader diagnostics set without auditing repos and writes a machine-readable JSON artifact to `output/diagnostics-<username>-<date>.json`.

For day-to-day operations, `--control-center` is now the clean read-only entrypoint. It reuses the latest report, review state, campaign history, governance drift, and setup health to build one shared operator queue without running a new audit or mutating any external system.

`pyproject.toml` is the canonical dependency definition, and `requirements.txt` is kept as a synchronized compatibility mirror for environments that still prefer a flat requirements file.

## Excel Workbook

The workbook now supports two modes:

- `--excel-mode template` — flagship workbook path using `assets/excel/analyst-template.xlsx`
- `--excel-mode standard` — fallback fully code-generated workbook for CI, debugging, or template-free environments

Both modes read from the same report + warehouse facts. The template-backed workbook owns the workbook shell, named-range bindings, native sparkline placement, and print layout. Python owns the hidden `Data_*` sheets, stable table names, and workbook facts.

Template mode is also validated during preflight: the committed workbook asset must exist and pass a lightweight shell check before the run will continue.

## Managed Campaigns and Governance

Campaign writeback is now lifecycle-aware rather than one-shot:

- `--campaign-sync-mode reconcile` updates active managed records and closes stale ones
- `--campaign-sync-mode append-only` leaves stale managed records open and marks them stale
- `--campaign-sync-mode close-missing` aggressively closes previously managed records that no longer belong in the campaign

Managed state drift, rollback coverage, and campaign history are written into JSON, Markdown, HTML, Excel, and the warehouse snapshot. Governed security controls still remain manual and opt-in, but operator surfaces now distinguish ready, approved, applied, drifted, and rollback coverage states when governance data is present.

When writeback or governance-related actions are requested, preflight checks now validate the required GitHub and Notion prerequisites before any external mutation path starts.

## Operator Loop

The daily operator loop is now:

- Run `audit <github-username> --control-center`
- Clear anything in `Blocked` first
- Review `Needs Attention Now` for drift and high-severity changes
- Work through `Ready for Manual Action`
- Leave `Safe to Defer` items alone unless priorities change

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
