# GitHub Repo Auditor

Automated audit tool that clones all repos from a GitHub user account, analyzes each repo across 9 completeness dimensions, and generates structured audit reports (JSON + Markdown).

Built for a solo developer who maintains 100+ project ideas and needs ground-truth metrics on what's actually shipped vs abandoned.

## Quick Start

```bash
pip install -r requirements.txt
python -m src saagpatel
```

## Requirements

- Python 3.11+
- `requests` and `python-dateutil` (`pip install -r requirements.txt`)
- GitHub token: set `GITHUB_TOKEN` env var, or have the `gh` CLI authenticated

## CLI

```
python -m src <username> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `username` | *(required)* | GitHub username to audit |
| `--token` | `$GITHUB_TOKEN` / `gh auth token` | Personal access token for private repos + rate limits |
| `--output-dir` | `output/` | Directory for report files |
| `--skip-forks` | off | Exclude forked repos |
| `--skip-archived` | off | Exclude archived repos |
| `--skip-clone` | off | Metadata fetch only (no clone or analysis) |
| `--registry PATH` | none | Cross-reference against a project-registry.md file |
| `--no-cache` | off | Bypass the 1-hour API response cache |
| `--verbose` | off | Print per-dimension score breakdown to stderr |

## Output Files

| File | Format | Description |
|------|--------|-------------|
| `audit-report-{user}-{date}.json` | JSON | Full audit report with summary statistics |
| `audit-report-{user}-{date}.md` | Markdown | Human-readable report with tier tables and per-repo details |
| `pcc-import-{user}-{date}.json` | JSON | Flat array for dashboard import |
| `raw_metadata.json` | JSON | Backwards-compatible raw audit data |

## Scoring Dimensions

Each analyzer scores 0.0–1.0. The overall score is a weighted average.

| Dimension | Weight | What It Checks |
|-----------|--------|---------------|
| README Quality | 15% | Exists, description, install instructions, code examples, badges |
| Project Structure | 10% | .gitignore, source dirs, config files, LICENSE, directory depth |
| Code Quality | 15% | Entry point, TODO density, type definitions, vendored files, commit messages |
| Testing | 15% | Test dirs/files, framework configured, test file count |
| CI/CD | 10% | GitHub Actions, alternative CI, build scripts |
| Dependencies | 10% | Lockfile, manifest, dependency count |
| Activity | 15% | Push recency, commit count, recent commits, archived status |
| Documentation | 5% | docs/ dir, CHANGELOG, CONTRIBUTING, comment density |
| Build Readiness | 5% | Docker, Makefile, .env.example, deploy config |

## Completeness Tiers

| Tier | Score Range | Description |
|------|-------------|-------------|
| Shipped | 0.75 – 1.0 | Production-ready. README, tests, CI, recent activity. |
| Functional | 0.55 – 0.74 | Works but rough edges. Missing tests or CI. |
| WIP | 0.35 – 0.54 | Partially built. Some structure, incomplete. |
| Skeleton | 0.15 – 0.34 | Scaffolded but barely started. |
| Abandoned | 0.0 – 0.14 | No meaningful content or activity. |

**Override rules:** Archived repos capped at Functional. Repos with no push in 2+ years capped at WIP. Repos with only a README forced to Skeleton.

## Registry Reconciliation

With `--registry`, the tool cross-references GitHub repos against a local project registry file to identify:

- Repos on GitHub that aren't tracked in the registry
- Projects in the registry that have no matching GitHub repo
- A status alignment matrix showing where registry status and audit tier agree or diverge

## Caching

API responses are cached to `output/.cache/` with a 1-hour TTL. This makes repeat runs significantly faster (only cloning + analysis, no API calls). Use `--no-cache` to force fresh API requests.
