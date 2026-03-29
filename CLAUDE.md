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
Phases 0–22 complete. 444+ tests, 44 test files, 12+ analyzers (extensible via --analyzers-dir plugin API), 47 CLI flags. Outputs: JSON, Markdown, Excel (22+ sheets), HTML dashboard, PDF report. GitHub Actions CI + scheduled weekly audit. Config file, watch mode, dry-run, resume, terminal diff summary, GitHub Issues auto-creation, OSV.dev vulnerability checking, code complexity trends. Full Notion two-way sync, shields.io badges, AI narrative, scoring profiles, archive automation. Portfolio improvement campaign: manifest generation, batch metadata/README updates via Contents API.

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
