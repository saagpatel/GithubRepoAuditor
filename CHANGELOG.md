# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

---

## [Unreleased]

## [0.18.0] - 2026-03-29
### Added
- Excel radar chart sheet for per-repo dimension scores
- Security surface sheet in Excel export
- Historical diff sheet comparing audit runs over time
- Notion two-way sync: pull Notion project metadata back into audit scores
- Notion dashboard page generated from audit results

### Fixed
- Scatter chart generation now uses `add_data`/`set_categories` openpyxl API correctly
- A grade threshold calibrated from 0.85 to 0.80 for more realistic portfolio grading
- XCTest file counting, Swift CI detection, and clone isolation regression bugs

## [0.17.0] - 2026-03-29
### Added
- Cross-repo similarity detection using TF-IDF on README content
- Archive automation: identify and batch-archive abandoned repos via GitHub API
- Scoring profiles: `lightweight`, `comprehensive`, and `ci` modes with different weight sets
- AI-generated narrative summaries per repo using Anthropic API (`--ai-narrative` flag)
- Notion sync history tracking — audit results stored as versioned Notion pages

## [0.16.0] - 2026-03-29
### Added
- Interactive HTML dashboard with filterable, sortable repo table
- Tech radar visualization embedded in HTML export
- `--html` flag to emit `output/dashboard-{username}-{date}.html`

## [0.15.0] - 2026-03-29
### Added
- Deep Notion integration: automated recommendation pages, action items, weekly review digest
- Notion registry sync: bidirectional mapping between GitHub repos and Notion project database
- `--notion-review` flag for weekly health digest

## [0.14.0] - 2026-03-29
### Added
- Security surface analyzer (`src/analyzers/security.py`): detects hardcoded secrets, exposed env files, overly-permissive configs
- README improvement suggestions engine (`src/readme_suggestions.py`): per-repo actionable diff
- `--readme-suggest` flag to emit inline suggestions in Markdown report

## [0.13.0] - 2026-03-29
### Added
- Notion external signal integration: pulls star counts, watchers, and topic metadata from Notion
- Portfolio README generator (`src/portfolio_readme.py`): auto-generates a GitHub profile README from audit data

## [0.12.0] - 2026-03-28
### Added
- Rich terminal output with color-coded tier badges, progress bars, and summary panels
- Unicode sparklines for commit activity trends in CLI output (`src/sparkline.py`)

## [0.11.0] - 2026-03-28
### Added
- Shields.io badge generation per repo (`src/badge_export.py`)
- Optional Gist upload for badge URLs via `--badges-gist` flag

## [0.10.0] - 2026-03-28
### Added
- Portfolio-relative language novelty adjustment in interest scoring
- Tuned burst detection for commit frequency spikes
- Scatter chart in Excel export: completeness vs. interest per repo

## [0.9.0] - 2026-03-28
### Added
- Narrative dashboard: plain-English summary of portfolio health
- Action items section in Markdown report: prioritized improvement list per repo
- Incremental audit mode (`--incremental`): re-analyze only repos changed since last run

## [0.8.0] - 2026-03-28
### Added
- Targeted audit: `--repos` flag to audit a comma-separated list of repos instead of the full portfolio
- Fast single-repo update path that skips unchanged repos

## [0.7.0] - 2026-03-25
### Added
- Flagship Excel dashboard with 10 sheets and a full design system (`src/excel_export.py`, `src/excel_styles.py`)
- Sheets: Summary, All Repos, Tier Breakdown, Top/Bottom 10, Language Distribution, Activity Heatmap, Dimension Radar

## [0.6.0] - 2026-03-25
### Added
- GraphQL client (`src/graphql_client.py`) for bulk repo queries, reducing API call count
- Library-years (libyears) staleness metric via `src/libyears.py`
- GitHub Releases detection in activity analyzer
- Radon cyclomatic complexity scoring in code quality analyzer
- Technology stack summary in report
- Trend tracking: week-over-week score deltas

## [0.5.0] - 2026-03-25
### Added
- Letter grades A–F for individual repos and portfolio health (`src/scorer.py`)
- Badge system: earned badges per repo based on dimension scores (`src/badges.py`)
- Quick wins: lowest-effort improvements highlighted per repo (`src/quick_wins.py`)
- Commit pattern analysis: message quality, burst detection, solo vs. team commits
- Bus factor estimation from contributor stats

## [0.4.0] - 2026-03-25
### Added
- Dual-axis scoring: independent completeness and interest scores per repo
- Auto-sync: background re-audit of stale repos on a configurable schedule
- Audit history persistence across runs (`src/history.py`)
- Test suite expanded to 82 tests

## [0.3.1] - 2026-03-24
### Added
- Early Excel dashboard with 6 sheets and 6 charts
- Historical diff view: score changes between two audit runs (`src/diff.py`)
- Swift/iOS-specific analyzer tuning
- CI pipeline for the auditor itself (GitHub Actions)

## [0.3.0] - 2026-03-24
### Added
- Registry reconciliation: cross-reference GitHub repos against a local `project-registry.md`
- `--registry` flag to specify the registry path
- GitHub API response cache (`src/cache.py`) with 1-hour TTL stored in `output/.cache/`
- Summary statistics: most active, most neglected, highest/lowest scored, language distribution

## [0.2.0] - 2026-03-24
### Added
- JSON audit report (`output/audit-report-{username}-{date}.json`) matching `AuditReport` schema
- Markdown report with summary table, tier-grouped repo lists, and per-repo detail sections
- PCC-compatible flat JSON export (`output/pcc-import-{username}-{date}.json`)
- `--skip-forks` flag
- `--output-dir` flag
- Progress output on stderr: `[12/47] Analyzing repo-name...`

## [0.1.0] - 2026-03-24
### Added
- Initial release: GitHub API client with pagination and rate-limit handling (`src/github_client.py`)
- Shallow clone pipeline via subprocess (`src/cloner.py`)
- `argparse` CLI entry point (`src/cli.py`)
- `RepoMetadata`, `AnalyzerResult`, `RepoAudit`, `AuditReport` dataclasses (`src/models.py`)
- 9 completeness analyzers: `readme`, `structure`, `code_quality`, `testing`, `cicd`, `dependencies`, `activity`, `documentation`, `build_readiness`
- `InterestAnalyzer` for tech novelty and project ambition scoring
- Weighted composite scorer with completeness tier classification (`src/scorer.py`)
- JSON and Markdown report output (`src/reporter.py`)
