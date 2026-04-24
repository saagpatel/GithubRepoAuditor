# GitHub Repo Auditor

## Overview
Automated audit tool that clones all repos from a GitHub user account, analyzes each repo across 10+ completeness dimensions, and generates a structured audit report (JSON + Markdown). Built for a solo developer who maintains 100+ project ideas and needs ground-truth metrics on what's actually shipped vs abandoned on GitHub.

## Tech Stack
- Python: 3.11+
- GitHub API: REST v3 via `requests` (no PyGithub — keep it lean)
- Git: CLI via `subprocess` for cloning
- Analysis: Pure Python + `pathlib` for file inspection
- Output: JSON (machine-readable) + Markdown (human-readable report)

## Development Conventions
- Python: Type hints on all functions, f-strings, pathlib over os.path
- File naming: snake_case for all Python files
- Git commits: conventional commits — feat:, fix:, chore:
- No external analysis frameworks — keep dependencies minimal
- All output files go to `output/` directory

## Current State
Phases 0–26 complete. 456 tests, 43 test files, 11 analyzers (extensible via --analyzers-dir plugin API), 51 CLI flags. Outputs: JSON, Markdown, Excel (55 sheets, 36-column All Repos), HTML dashboard, PDF report. GitHub Actions CI + scheduled weekly audit. Config file, watch mode, dry-run, resume, terminal diff summary, GitHub Issues auto-creation, OSV.dev vulnerability checking, code complexity trends. Full Notion two-way sync, shields.io badges, AI narrative, scoring profiles, archive automation. Portfolio improvement campaigns: batch metadata/README/governance/build-readiness/community-profile updates via Contents API. Phase 26: community profile — CODE_OF_CONDUCT (104 repos), issue templates (101 repos), PR template (105 repos), CHANGELOG (76 repos), stale branch cleanup.

## Key Decisions
| Decision | Choice | Why |
|----------|--------|-----|
| GitHub API auth | Personal Access Token via env var | Needed for private repos + rate limits |
| Clone strategy | Shallow clone (depth=1) | We only need current state, not history |
| Commit history | GitHub API for stats, not local git log | Faster than full clone, gets contributor + frequency data |
| Output format | JSON primary, Markdown derived | JSON feeds into PCC; Markdown for human review |
| Dependency scanning | Parse lockfiles directly | No need for `pip-audit` or `npm audit` — just detect staleness |

## Do NOT
- Do not use PyGithub or octokit — raw requests to keep deps minimal
- Do not full-clone repos — shallow clone (depth=1) only
- Do not hardcode the GitHub username — accept it as a CLI argument
- Do not skip private repos — use the token if provided
<!-- portfolio-context:start -->
# Portfolio Context

## What This Project Is

Python portfolio operator that audits GitHub repos across 10+ dimensions and packages a weekly story across Excel, Markdown, HTML dashboard, review-pack, control-center, and handoff surfaces. Ground-truth metrics on what's shipped vs abandoned across 100+ repos.

## Current State

Arc D (Phases 119-122) complete. Full local suite is expected to stay green; rerun `python3 -m pytest -q -p no:cacheprovider` for the current test count before reporting release status. Bounded-automation infrastructure wired — `--auto-apply-approved` flag with trust bar (automation_eligible + baseline risk + trusted decision quality). Weekly command center, portfolio truth snapshot, operator control center, warehouse all operational.

## Stack

- Python 3.11+, requests, pathlib, sqlite3
- Output: JSON + Markdown + Excel (openpyxl, 55 sheets) + HTML + PDF
- GitHub REST API v3 (no PyGithub), GitHub Contents API for writeback
- Notion API for two-way sync

## How To Run

```
uv run python -m src.cli <github_username> [flags]
uv run pytest
python -m ruff check src/ tests/
```

Common flags: `--control-center`, `--portfolio-truth`, `--portfolio-context-recovery`, `--campaign <name> --writeback-target github`, `--campaign <name> --writeback-target all --github-projects`, `--approval-center`, `--auto-apply-approved --dry-run`.

## Known Risks

- GitHub API rate limit (5000/hr authenticated): full-portfolio runs on large accounts may need --resume
- Excel workbook generation is slow on 100+ repos (openpyxl, no streaming)
- Portfolio-truth sources depend on local workspace scan — must be run from the machine that has repos cloned
- Auto-apply trust bar is new (Arc D) — not yet battle-tested across multiple cycles

## Next Recommended Move

Complete manual workbook signoff if the 2026-04-24 rehearsal should become a release record, then prepare Phase 123 by selecting 2-3 low-risk catalog-opted repos, confirming approval-center readiness, and rerunning `--auto-apply-approved --dry-run` before any live apply. See docs/plans/2026-04-24-phase-123-readiness-prep.md, docs/plans/2026-04-24-post-merge-current-state.md, and docs/plans/2026-04-15-arc-d-closeout.md for the current gates and Arc E/F/G sequencing.
<!-- portfolio-context:end -->
