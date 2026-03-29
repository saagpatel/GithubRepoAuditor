# GitHub Repo Auditor

[![Python](https://img.shields.io/badge/Python-%233776ab?style=flat-square&logo=python)](#) [![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](#) [![Tests](https://img.shields.io/badge/tests-426%20passing-brightgreen?style=flat-square)](#)

> Know the truth about every project you've ever started — because `git log` across 100 repos doesn't tell you which ones are worth finishing.

GitHub Repo Auditor clones every repo on your GitHub account, runs 12 analyzers across completeness and interest dimensions, assigns letter grades and achievement badges, and generates actionable dashboards you can actually use to decide what to work on next. Built for developers who ship fast, start often, and need a system to manage the sprawl.

## Features

- **12 Analyzers** — README quality, test coverage, CI/CD, dependency freshness, commit patterns, bus factor, code complexity, security controls, license, build readiness, GraphQL signals, and more
- **Dual-Axis Scoring** — Completeness (does this project have what shipped software should?) and Interest (is this worth anyone's time?) scored independently on 0.0–1.0 scales
- **Letter Grades + Tier Classification** — A–F grades with Shipped / Functional / WIP / Skeleton / Abandoned tiers; 15 achievement badges ("Fully Tested", "CI Champion", "Zero Debt", etc.)
- **Quick Wins Engine** — For each repo, shows exactly which single action moves it to the next tier and how far it is from getting there
- **Multiple Dashboard Outputs** — Flagship Excel workbook with `template` and `standard` modes, interactive HTML dashboard with scatter chart and tech radar, portfolio README, shields.io badges
- **Notion Integration** — Pushes audit signals into your Notion operating system: completeness cards, governed issue requests, and weekly review enrichment
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
pip install -r requirements.txt
```

### Run

```bash
# Audit a GitHub user's repos
python -m src <github-username>

# Generate the native workbook + HTML dashboard
python -m src <github-username> --html --excel-mode template

# Dry run — no cloning, no writes
python -m src <github-username> --dry-run
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

## Excel Workbook

The workbook now supports two modes:

- `--excel-mode template` — flagship workbook path using `assets/excel/analyst-template.xlsx`
- `--excel-mode standard` — fallback fully code-generated workbook for CI, debugging, or template-free environments

Both modes read from the same report + warehouse facts. The template-backed workbook owns the workbook shell, named-range bindings, native sparkline placement, and print layout. Python owns the hidden `Data_*` sheets, stable table names, and workbook facts.

## License

MIT
