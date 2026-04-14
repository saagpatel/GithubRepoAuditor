# GitHub Repo Auditor

## Overview
Workbook-first portfolio operator that audits GitHub repos, scores implementation maturity, and packages one shared weekly story across workbook, Markdown, HTML, review-pack, control-center, and scheduled-handoff surfaces. Built for a solo developer who maintains 100+ project ideas and needs one truthful operating system for what is shipped, fragile, blocked, or safe to defer.

## Tech Stack
- Python: 3.11+
- GitHub API: REST v3 via `requests` (no PyGithub — keep it lean)
- Git: CLI via `subprocess` for cloning
- Analysis: Pure Python + `pathlib` for file inspection
- Output: workbook + JSON + Markdown + HTML + review-pack + scheduled handoff

## Development Conventions
- Python: Type hints on all functions, f-strings, pathlib over os.path
- File naming: snake_case for all Python files
- Git commits: conventional commits — feat:, fix:, chore:
- No external analysis frameworks — keep dependencies minimal
- All output files go to `output/` directory

## Current State
Workbook-first portfolio operator system with shared workbook, Markdown, HTML, review-pack, control-center, and scheduled-handoff surfaces. The repo now includes Action Sync guidance, local approval workflow support, warehouse-backed history, and a shared `weekly_story_v1` packaging seam. Use the active roadmap docs under `docs/plans/` as the source of truth for current phase status, deferred work, and closeout workflow instead of relying on hardcoded phase numbers here.

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
