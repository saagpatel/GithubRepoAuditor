# GitHub Repo Auditor

**Know the truth about every project you've ever started.**

If you're a developer with 50, 80, 100+ repositories — some shipped, some half-built, some you forgot existed — this tool gives you the ground truth. It clones every repo, runs 11 analyzers, scores across two axes, assigns letter grades and achievement badges, and generates a flagship Excel dashboard you can actually use to decide what to work on next.

Built for the developer who ships fast and starts often, and needs a system to keep track of it all.

## What It Does

1. **Fetches every repo** on your GitHub (public + private) via REST or GraphQL
2. **Shallow-clones each one** and inspects the actual files
3. **Scores on two axes:**
   - **Completeness** (0.0–1.0) — Does this project have what a real project should? README, tests, CI, dependencies, structure, docs, build readiness.
   - **Interest** (0.0–1.0) — Is this project actually interesting? Novel tech, commit passion, ambitious scope, storytelling README, external validation.
4. **Assigns letter grades** (A–F) and classifies into tiers (Shipped / Functional / WIP / Skeleton / Abandoned)
5. **Awards 15 achievement badges** — "Fully Tested", "CI Champion", "Novel Tech", "Zero Debt", "Complete Package", etc.
6. **Tells you exactly what to do next** — Quick Wins show which repos are closest to the next tier and what specific action gets them there
7. **Generates a flagship Excel dashboard** — 10 sheets with KPI cards, heatmaps, badge boards, tech stack proficiency, and more
8. **Cross-references against your project registry** — finds repos not tracked locally and projects without matching repos
9. **Tracks history** — archives every audit run and auto-diffs against the previous to surface regressions and improvements

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

Every run produces 5 files:

| File | What It Is |
|------|-----------|
| `audit-report-{user}-{date}.json` | Full structured audit — every score, badge, finding, and dimension detail |
| `audit-report-{user}-{date}.md` | Human-readable Markdown with tier tables, quick wins, and collapsible per-repo breakdowns |
| `audit-dashboard-{user}-{date}.xlsx` | **The flagship** — 10-sheet Excel workbook (see below) |
| `pcc-import-{user}-{date}.json` | Flat array for importing into dashboards or project management tools |
| `raw_metadata.json` | Backwards-compatible raw audit data |

### The Excel Dashboard

This is the centerpiece. Open it instead of reading JSON.

| Sheet | What You See |
|-------|-------------|
| **Dashboard** | Portfolio grade, 6 KPI cards, tier pie chart, grade distribution, language breakdown, best work highlights |
| **All Repos** | Sortable 20-column master table with inline score bars, grade coloring, badge counts, next-badge suggestions, commit patterns |
| **Scoring Heatmap** | Every repo × every dimension, color-coded red→amber→green. Spot weaknesses at a glance. |
| **Quick Wins** | Repos within striking distance of the next tier, with the exact actions to get there |
| **Badges** | Portfolio-wide badge distribution chart + achievement leaderboard |
| **Tech Stack** | Language proficiency weighted by project quality, best work top 5 |
| **Trends** | Score and tier evolution across audit runs (after 2+ runs) |
| **Tier Breakdown** | Per-tier deep dive with grades and descriptions |
| **Activity** | Commit patterns, bus factor, release cadence, push recency |
| **Registry** | Cross-reference with your local project registry |

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
| `--registry PATH` | none | Cross-reference against a project-registry.md |
| `--sync-registry` | off | Auto-add untracked repos to the registry |
| `--skip-forks` | off | Exclude forked repos |
| `--skip-archived` | off | Exclude archived repos |
| `--skip-clone` | off | Metadata only, no file analysis |
| `--no-cache` | off | Bypass the 1-hour API response cache |
| `--diff PATH` | none | Compare against a specific previous report |
| `--verbose` | off | Print per-dimension score breakdown to stderr |

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

### Interest Score (separate axis, 7 signals)

| Signal | What It Detects |
|--------|----------------|
| Description quality | Specific, detailed project descriptions |
| Topic tags | Repos with curated topic metadata |
| Tech novelty | Uncommon languages (Rust, Swift, GDScript), multi-language repos |
| Commit bursts | High-variance commit patterns indicating passionate development |
| Project ambition | Multi-module structure, real dependencies, significant LOC, creative assets |
| External validation | Stars, forks |
| README storytelling | Long READMEs with images or diagrams |

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
| A | 0.85+ |
| B | 0.70–0.84 |
| C | 0.55–0.69 |
| D | 0.35–0.54 |
| F | <0.35 |

### Portfolio Health Grade

Not just a simple average — accounts for language diversity (+bonus), shipped ratio (+bonus), abandonment rate (-penalty), and badge density (+bonus).

## Badges

15 achievements a repo can earn:

| Badge | How to Earn |
|-------|------------|
| `fully-tested` | Testing score ≥ 0.8 |
| `well-documented` | README ≥ 0.8 AND docs ≥ 0.5 |
| `ci-champion` | CI/CD score ≥ 0.8 |
| `dependency-disciplined` | Dependencies score ≥ 0.8 |
| `fresh` | Pushed within 30 days |
| `battle-tested` | Testing ≥ 0.8 AND 10+ test files |
| `complete-package` | All dimensions ≥ 0.5 |
| `novel-tech` | Uncommon language or 3+ language repo |
| `storyteller` | README >1000 chars with images/diagrams |
| `community-ready` | Community profile ≥ 0.6 |
| `zero-debt` | TODO density < 1 per 1000 LOC |
| `actively-maintained` | Activity score ≥ 0.8 |
| `built-to-ship` | Build readiness ≥ 0.6 |
| `polyglot` | 3+ languages in repo |
| `has-fans` | Stars > 0 or forks > 0 |

The tool also suggests which badge is closest to being earned and what action would unlock it.

## Caching & Performance

- API responses cached to `output/.cache/` with 1-hour TTL
- Registry lookups cached at 24-hour TTL
- `--graphql` mode fetches all repos in 1-2 queries instead of 100+ REST calls
- Repeat runs with cache hit skip API entirely — only cloning and analysis

## History & Diffs

Every audit run is archived to `output/history/`. On subsequent runs, the tool automatically compares against the most recent archive and surfaces:
- New and removed repos
- Tier transitions (promoted or demoted)
- Score improvements and regressions
- Average score delta

The CI workflow creates a GitHub Issue if any regressions are detected.

## Registry Reconciliation

With `--registry ~/Projects/project-registry.md`:
- Fuzzy-matches GitHub repos to registry entries (handles name variations)
- Shows repos on GitHub not tracked in the registry
- Shows registry entries with no matching repo
- Generates a **status alignment matrix** comparing registry status vs audit tier

With `--sync-registry`, untracked repos are auto-added to the correct section based on language.

## Tech Stack

- **Python 3.11+** — type hints, pathlib, f-strings throughout
- **Dependencies:** `requests`, `python-dateutil`, `openpyxl`, `radon` — deliberately minimal
- **GitHub API:** REST v3 + optional GraphQL v4
- **Analysis:** Pure Python + pathlib for file inspection, radon for Python complexity
- **30 source files**, 5,767 lines of code
- **102 tests** across 11 test files

## CI/CD

Two GitHub Actions workflows:
- **CI** (`ci.yml`) — runs tests on every push to main
- **Scheduled Audit** (`audit.yml`) — weekly Monday 6am UTC, archives results, creates Issues on regressions
