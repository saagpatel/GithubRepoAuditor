# GitHub Repo Auditor

![Grade](https://img.shields.io/badge/grade-A-brightgreen) ![Tier](https://img.shields.io/badge/tier-shipped-brightgreen) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![Tests](https://img.shields.io/badge/tests-304%20passing-brightgreen)

**Know the truth about every project you've ever started.**

If you're a developer with 50, 80, 100+ repositories — some shipped, some half-built, some you forgot existed — this tool gives you the ground truth. It clones every repo, runs 12 analyzers, scores across two axes, assigns letter grades and achievement badges, and generates an interactive dashboard you can actually use to decide what to work on next.

Built for the developer who ships fast and starts often, and needs a system to keep track of it all.

## What It Does

1. **Fetches every repo** on your GitHub (public + private) via REST or GraphQL
2. **Shallow-clones each one** and inspects the actual files
3. **Scores on two axes:**
   - **Completeness** (0.0–1.0) — Does this project have what a real project should? README, tests, CI, dependencies, structure, docs, build readiness.
   - **Interest** (0.0–1.0) — Is this project actually interesting? Novel tech, commit passion, ambitious scope, storytelling README, external validation.
4. **Assigns letter grades** (A–F) and classifies into tiers (Shipped / Functional / WIP / Skeleton / Abandoned)
5. **Awards 15 achievement badges** — "Fully Tested", "CI Champion", "Novel Tech", "Zero Debt", "Complete Package", etc.
6. **Builds security intelligence** — exposed secrets, dangerous files, GitHub-native security controls, SBOM availability, and optional Scorecard enrichment
7. **Tells you exactly what to do next** — Quick Wins show which repos are closest to the next tier and what specific action gets them there
8. **Generates multiple dashboards:**
   - Flagship Excel workbook with analyst, security, and governance sheets
   - Interactive HTML dashboard (scatter chart, filterable table, tech radar, security overview)
   - Shields.io badges for GitHub READMEs
   - Portfolio README for your GitHub profile
9. **Integrates with Notion** — pushes audit signals into your Notion operating system: recommendations, governed issue requests, weekly review enrichment, project completeness cards
10. **Tracks history and warehouse snapshots** — archives every audit run, auto-diffs, persists a SQLite warehouse, detects regressions, identifies archive candidates
11. **AI-powered narrative** — feeds audit data to Claude for a human-readable portfolio analysis

## Why This Exists

Because `git log` across 100 repos doesn't tell you which projects are worth finishing. Because starring your own repos doesn't count as shipping. Because the difference between a "shipped" project and a "skeleton" is measurable — and once you measure it, you can fix it.

This tool turns your GitHub account from a graveyard of good intentions into a managed portfolio with clear priorities.

## Quick Start

```bash
git clone https://github.com/saagpatel/GithubRepoAuditor.git
cd GithubRepoAuditor
pip install -r requirements.txt
python -m src <your-github-username>
```

The tool auto-detects your GitHub token from `$GITHUB_TOKEN` or the `gh` CLI. For private repos and higher rate limits, make sure one of those is set.

## Output

Every run produces 6 core files, plus optional exports:

| File | What It Is |
|------|-----------|
| `audit-report-{user}-{date}.json` | Full structured audit — every score, badge, finding, and dimension detail |
| `audit-report-{user}-{date}.md` | Human-readable Markdown with tier tables, quick wins, and collapsible per-repo breakdowns |
| `audit-dashboard-{user}-{date}.xlsx` | Flagship 12-sheet Excel workbook (see below) |
| `pcc-import-{user}-{date}.json` | Flat array for importing into dashboards or project management tools |
| `raw_metadata.json` | Backwards-compatible raw audit data |
| `portfolio-warehouse.db` | SQLite warehouse snapshot for downstream analysis, compare flows, and future operations |

### Optional Exports

| Flag | Output |
|------|--------|
| `--badges` | `output/badges/` — shields.io badge JSON + `badges.md` with copy-pasteable markdown |
| `--upload-badges` | Uploads badge JSON to a GitHub Gist for auto-updating endpoint badges |
| `--html` | `output/dashboard-{user}-{date}.html` — self-contained interactive dashboard |
| `--review-pack` | `output/review-pack-{user}-{date}.md` — concise analyst/security review artifact |
| `--portfolio-readme` | `output/PORTFOLIO.md` — GitHub profile-ready readme with badges and tier-grouped repos |
| `--readme-suggestions` | `output/readme-suggestions-{date}.md` — per-repo actionable README improvements |
| `--notion` | `output/notion-audit-events-{date}.json` — normalized events for Notion signal pipeline |
| `--notion-sync` | Pushes events + recommendations + action requests to Notion API |
| `--narrative` | `output/narrative-{date}.md` — AI-generated portfolio analysis (requires `ANTHROPIC_API_KEY`) |
| `--auto-archive` | `output/archive-candidates-{date}.md` — repos below 0.15 for 3+ consecutive runs |

### The Excel Dashboard

This is the centerpiece. Open it instead of reading JSON.

| Sheet | What You See |
|-------|-------------|
| **Dashboard** | Portfolio grade, 6 KPI cards, tier pie chart, grade distribution, language breakdown, completeness vs interest scatter chart, portfolio sparkline |
| **All Repos** | Sortable 23-column master table with inline score bars, grade coloring, badge counts, commit patterns, trend sparklines |
| **Scoring Heatmap** | Every repo x every dimension, color-coded red-amber-green. Spot weaknesses at a glance. |
| **Quick Wins** | Repos within striking distance of the next tier, with the exact actions to get there |
| **Badges** | Portfolio-wide badge distribution chart + achievement leaderboard |
| **Tech Stack** | Language proficiency weighted by project quality, best work top 5 |
| **Trends** | Score and tier evolution across audit runs (after 2+ runs) |
| **Tier Breakdown** | Per-tier deep dive with grades and descriptions |
| **Activity** | Commit patterns, bus factor, release cadence, push recency |
| **Security Controls** | SECURITY.md, Dependabot, dependency graph, SBOM, code scanning, and secret scanning status by repo |
| **Supply Chain** | Security score, Scorecard coverage, dependency graph/SBOM posture, and top supply-chain recommendation |
| **Security Debt** | Dry-run governance queue for the highest-value security remediations |
| **Portfolio Explorer** | Profile-aware ranking, hotspot count, and collection membership |
| **By Lens** | Repo rankings split by decision lens |
| **Scenario Planner** | Profile/collection-based lift preview |
| **Executive Summary** | Analyst-friendly summary view with leaders, movers, and scenario preview |
| **Registry** | Cross-reference with your local project registry |
| **Score Explainer** | How scoring, grades, and tiers work |
| **Action Items** | Prioritized improvements with effort estimates |

### The HTML Dashboard

A single self-contained HTML file with embedded CSS and JavaScript. No external dependencies — works offline, shareable as a link.

- Canvas2D scatter chart (completeness vs interest, colored by tier, hover tooltips)
- Filterable and sortable repo table with profile- and collection-aware ranking
- Tech radar showing language adoption trends (Adopt / Trial / Hold / Decline)
- Security overview cards and dry-run governance preview
- Tier distribution bar charts
- Print-friendly CSS — use browser "Print to PDF" for a clean report

## CLI

```
python -m src <username> [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `username` | *(required)* | GitHub username to audit |
| `--token` | `$GITHUB_TOKEN` / `gh auth token` | Personal access token |
| `--output-dir` | `output/` | Where reports go |
| `--graphql` | off | Use GraphQL for faster bulk fetch (1-2 queries vs 100+ REST calls) |
| `--repos REPO [...]` | all | Audit only specific repos by name or URL |
| `--incremental` | off | Only re-audit repos that changed since last run |
| `--registry PATH` | none | Cross-reference against a project-registry.md |
| `--notion-registry` | off | Use Notion Local Portfolio Projects as registry source |
| `--sync-registry` | off | Auto-add untracked repos to the registry |
| `--skip-forks` | off | Exclude forked repos |
| `--skip-archived` | off | Exclude archived repos |
| `--skip-clone` | off | Metadata only, no file analysis |
| `--no-cache` | off | Bypass the 1-hour API response cache |
| `--diff PATH` | none | Compare against a specific previous report |
| `--verbose` | off | Print per-dimension score breakdown to stderr |
| `--scoring-profile NAME` | default | Use custom weights from `config/scoring-profiles/NAME.json` |
| `--portfolio-profile NAME` | `default` | Apply a ranking overlay for analyst-facing outputs |
| `--collection NAME` | none | Filter analyst-facing outputs to a named default collection |
| `--review-pack` | off | Generate a concise analyst/security review pack |
| `--scorecard` | off | Enrich eligible public repos with OpenSSF Scorecard data |
| `--security-offline` | off | Use local security analysis only and skip GitHub-native/external security enrichment |
| `--badges` | off | Generate shields.io badge JSON and markdown |
| `--upload-badges` | off | Upload badges to GitHub Gist (implies --badges) |
| `--html` | off | Generate interactive HTML dashboard |
| `--portfolio-readme` | off | Generate PORTFOLIO.md for GitHub profile |
| `--readme-suggestions` | off | Generate per-repo README improvement suggestions |
| `--notion` | off | Generate Notion event JSON (dry-run) |
| `--notion-sync` | off | Push audit events to Notion API (implies --notion) |
| `--narrative` | off | Generate AI portfolio narrative (requires ANTHROPIC_API_KEY) |
| `--auto-archive` | off | Generate archive candidate report |

## Scoring

### 10 Completeness Dimensions (weighted, sum = 1.0)

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Testing | 18% | Test directories, framework configured, test file count |
| Code Quality | 15% | Entry points, TODO density, type definitions, vendored files, commit messages, conventional commits, PR merge ratio, Radon complexity (Python) |
| Activity | 15% | Push recency, commit count, recent commits, release frequency, bus factor, commit pattern |
| README | 12% | Exists, description quality, install instructions, code examples, badges |
| Structure | 10% | .gitignore, language-standard dirs (including Xcode), config files, LICENSE, depth |
| CI/CD | 10% | GitHub Actions, alternative CI, build/test scripts |
| Dependencies | 8% | Lockfile, manifest, dep count, libyears freshness |
| Build Readiness | 7% | Dockerfile, Makefile, .env.example, deploy config |
| Community Profile | 3% | GitHub health files via `/community/profile` API |
| Documentation | 2% | docs/ dir, CHANGELOG, CONTRIBUTING, comment density |

Custom weight profiles can be created in `config/scoring-profiles/` for different contexts (job search, shipping focus, etc.).

### Additional Dimensions (advisory, not part of completeness)

| Dimension | What It Measures |
|-----------|-----------------|
| **Interest** | Tech novelty, commit bursts, project ambition, README storytelling, external validation, recency. Portfolio-relative: common "novel" languages get less credit. |
| **Security** | Exposed secrets, dangerous committed files, SECURITY.md, Dependabot config, GitHub-native security controls, SBOM availability, and optional Scorecard signals |

### Security Intelligence

Security posture now merges multiple providers:

- **Local** — committed secrets, dangerous files, SECURITY.md, Dependabot config
- **GitHub-native** — dependency graph/SBOM availability, code scanning, secret scanning, control coverage
- **Scorecard** — optional public-repo enrichment for a curated set of external security hygiene checks

Unavailable providers are treated as **unavailable evidence**, not as an automatic failure. The merged `security_posture` still preserves top-level `score` and `label` for backward compatibility while exposing provider-specific detail for dashboards and future dry-run governance.

### Tiers

| Tier | Score | Meaning |
|------|-------|---------|
| **Shipped** | 0.75+ | Production-ready. Tests, CI, docs, active. |
| **Functional** | 0.55–0.74 | Works but has gaps. |
| **WIP** | 0.35–0.54 | Partially built. |
| **Skeleton** | 0.15–0.34 | Scaffolded, barely started. |
| **Abandoned** | <0.15 | No meaningful content. |

Overrides: archived repos capped at Functional. Stale >2 years capped at WIP. README-only forced to Skeleton.

### Letter Grades

| Grade | Score |
|-------|-------|
| A | 0.80+ |
| B | 0.70–0.79 |
| C | 0.55–0.69 |
| D | 0.35–0.54 |
| F | <0.35 |

### Portfolio Health Grade

Not just a simple average — accounts for language diversity (+bonus), shipped ratio (+bonus), abandonment rate (-penalty), and badge density (+bonus).

## Badges

15 achievements a repo can earn:

| Badge | How to Earn |
|-------|------------|
| `fully-tested` | Testing score >= 0.8 |
| `well-documented` | README >= 0.8 AND docs >= 0.5 |
| `ci-champion` | CI/CD score >= 0.8 |
| `dependency-disciplined` | Dependencies score >= 0.8 |
| `fresh` | Pushed within 30 days |
| `battle-tested` | Testing >= 0.8 AND 10+ test files |
| `complete-package` | All dimensions >= 0.5 |
| `novel-tech` | Uncommon language or 3+ language repo |
| `storyteller` | README >1000 chars with images/diagrams |
| `community-ready` | Community profile >= 0.6 |
| `zero-debt` | TODO density < 1 per 1000 LOC |
| `actively-maintained` | Activity score >= 0.8 |
| `built-to-ship` | Build readiness >= 0.6 |
| `polyglot` | 3+ languages in repo |
| `has-fans` | Stars > 0 or forks > 0 |

The tool also suggests which badge is closest to being earned and what action would unlock it.

## Notion Integration

Integrates with the [Notion Operating System](https://github.com/saagpatel/notion-operating-system) to push audit intelligence into your portfolio management workflow:

- **Signal Events** — audit results flow into Notion's External Signal Events database as `provider: "Audit"` events
- **Derived Fields** — updates control tower projects with Audit Grade, Score, Interest, Badge Count, Date
- **Recommendations** — quick wins pushed to the Recommendation Runs database
- **Governed Actions** — critical gaps (no-tests, no-ci, no-readme) on shipped/functional repos create draft GitHub issue requests in Notion's approval pipeline
- **Weekly Review** — appends audit highlights to the most recent weekly review page
- **Completeness Cards** — appends dimension score summaries to individual project pages
- **Audit History** — tracks per-run metrics for Notion-native trend visualization
- **Registry Source** — `--notion-registry` queries Local Portfolio Projects for reconciliation instead of a markdown file

Requires `NOTION_TOKEN` environment variable and `config/notion-config.json` with database IDs.

## Cross-Repo Analysis

- **Similarity Detection** — hashes source files (SHA-256, first 4KB) across repos to find duplicates sharing >50% code
- **Tech Radar** — tracks language adoption trends across audit history (Adopt / Trial / Hold / Decline)
- **Archive Candidates** — identifies repos scoring below 0.15 for 3+ consecutive runs

## Caching & Performance

- API responses cached to `output/.cache/` with 1-hour TTL
- Registry lookups cached at 24-hour TTL
- `--graphql` mode fetches all repos in 1-2 queries instead of 100+ REST calls
- `--incremental` mode only re-audits repos whose `pushed_at` changed
- Rich progress bars with spinners and time elapsed (graceful fallback if `rich` not installed)

## History & Diffs

Every audit run is archived to `output/history/`. On subsequent runs, the tool automatically compares against the most recent archive and surfaces:
- New and removed repos
- Tier transitions (promoted or demoted)
- Score improvements and regressions
- Average score delta
- Unicode sparklines showing per-repo score trends across runs

## Tech Stack

- **Python 3.11+** — type hints, pathlib, f-strings throughout
- **Dependencies:** `requests`, `python-dateutil`, `openpyxl`, `radon`, `rich`, `anthropic` — deliberately minimal
- **GitHub API:** REST v3 + optional GraphQL v4
- **Analysis:** Pure Python + pathlib for file inspection, radon for Python complexity
- **~50 source files**, 249 tests
- **Zero JS framework dependencies** — HTML dashboard uses vanilla JS + Canvas2D
