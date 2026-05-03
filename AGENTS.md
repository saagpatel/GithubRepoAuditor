# GitHub Repo Auditor

## Communication Contract

- Follow `/Users/d/.codex/policies/communication/BigPictureReportingV1.md` for all user-facing updates.
- Use exact section labels from `BigPictureReportingV1.md` for default status/progress updates.
- Keep default updates beginner-friendly, big-picture, and low-noise.
- Keep technical receipts in durable artifacts or final verification summaries unless explicitly requested.

## Overview
Workbook-first portfolio operator that audits GitHub repos, scores implementation maturity, and packages one shared weekly story across workbook, Markdown, HTML, review-pack, control-center, and scheduled-handoff surfaces. Built for a solo developer who maintains 100+ project ideas and needs one truthful operating system for what is shipped, fragile, blocked, or safe to defer.

## First Read

- Read `README.md` for product modes, common commands, and operator workflow.
- Read `docs/plans/2026-04-24-post-merge-current-state.md` and the latest relevant file under `docs/plans/` before making roadmap or release claims.
- Check `git status` before editing; this repo is often touched by portfolio automation and parallel sessions.
- Use `.codex/verify.commands` as the canonical verification source for routine Codex work.

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
- Keep workbook, Markdown, HTML, review-pack, control-center, scheduled-handoff, and portfolio-truth surfaces aligned when changing shared packaging behavior.
- Treat writeback, Notion sync, GitHub Projects, approval capture, and auto-apply flows as high-risk; prefer dry-runs and explicit operator confirmation.

## Current State
Workbook-first portfolio operator system with shared workbook, Markdown, HTML, review-pack, control-center, and scheduled-handoff surfaces. The repo now includes Action Sync guidance, local approval workflow support, warehouse-backed history, and a shared `weekly_story_v1` packaging seam. Use the active roadmap docs under `docs/plans/` as the source of truth for current phase status, deferred work, and closeout workflow instead of relying on hardcoded phase numbers here.

## Codex App Usage

- Use Codex App Projects for repo-specific implementation, review, and verification in this checkout.
- Use a Worktree for risky changes to writeback, approval, auto-apply, portfolio-truth generation, workbook packaging, or multi-surface output contracts.
- Use artifacts for reusable operator reports, workbook signoff notes, release packets, and handoff summaries.
- Keep connectors read-first and task-scoped. Do not mutate GitHub, Notion, or local portfolio outputs unless the task explicitly authorizes that path.
- Use browser or screenshot evidence only when reviewing generated HTML or visual workbook/report output.
- Keep repo-local tests and `.codex/verify.commands` as the verification authority; Codex App tools add evidence but do not replace the repo gate.

## Verification

- `.codex/verify.commands` is the canonical verifier for routine Codex work.
- Current canonical verifier:
  - `python3 -m pytest -q -p no:cacheprovider`
  - `ruff check src/ tests/`
- Treat `mypy src/ --ignore-missing-imports` as an advisory modernization check until the existing type backlog is intentionally burned down.
- For workbook/output changes, also run the narrow generation or workbook gate command relevant to the changed surface.
- If a command is missing, unclear, or unsafe to run, stop and report the blocker instead of guessing.

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
- Do not run live writeback, Notion sync, GitHub Projects mutation, or auto-apply without explicit operator approval.
- Do not report release readiness from stale docs; rerun the verifier and inspect current state.
