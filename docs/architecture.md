# Architecture

GitHub Repo Auditor is a Python CLI tool that audits a GitHub user's entire repository portfolio. It fetches repo metadata from the GitHub REST API, shallow-clones each repo, runs 12 analysis dimensions over the local files, scores them on a dual-axis model (completeness + interest), and writes structured output in JSON, Markdown, Excel, and HTML formats.

## Typical Invocation

```bash
# Audit all public repos for a user
python3 -m src.cli saagpatel

# Audit with private repos and Notion sync
python3 -m src.cli saagpatel --token $GITHUB_TOKEN --notion

# Incremental re-audit of recently-changed repos only
python3 -m src.cli saagpatel --incremental

# Audit two specific repos with AI narrative
python3 -m src.cli saagpatel --repos my-app,my-lib --ai-narrative
```

---

## Project Structure

```
github-repo-auditor/
├── src/
│   ├── cli.py                  # argparse entry point — all 22 CLI flags defined here
│   ├── github_client.py        # REST API calls: list repos, commit stats, languages, releases
│   ├── graphql_client.py       # GraphQL bulk queries for batch metadata fetching
│   ├── cloner.py               # Shallow clone (depth=1) to temp dir + cleanup
│   ├── models.py               # RepoMetadata, AnalyzerResult, RepoAudit, AuditReport dataclasses
│   ├── scorer.py               # Weighted aggregation, tier classification, grade computation
│   ├── reporter.py             # JSON + Markdown report writers
│   ├── cache.py                # ResponseCache: disk-backed GitHub API response cache (1hr TTL)
│   ├── history.py              # Audit history persistence across runs
│   ├── diff.py                 # Score delta computation between two audit runs
│   ├── badges.py               # Badge award logic and badge catalog
│   ├── badge_export.py         # Shields.io badge URL generation + optional Gist upload
│   ├── excel_export.py         # Excel 3.0 exporter: standard renderer + template hydrator
│   ├── excel_template.py       # Template workbook helpers + native sparkline injection
│   ├── excel_styles.py         # Excel design system: colors, fonts, named styles
│   ├── web_export.py           # Interactive HTML dashboard generation
│   ├── narrative.py            # AI-generated plain-English repo summaries (Anthropic API)
│   ├── similarity.py           # TF-IDF cross-repo similarity detection
│   ├── archive_candidates.py   # Identify + batch-archive abandoned repos via GitHub API
│   ├── quick_wins.py           # Per-repo lowest-effort improvement suggestions
│   ├── readme_suggestions.py   # README improvement diff generation
│   ├── portfolio_readme.py     # GitHub profile README generator from audit data
│   ├── libyears.py             # Library-years dependency staleness metric
│   ├── sparkline.py            # Text sparklines for terminal and non-Excel surfaces
│   ├── cli_output.py           # Rich terminal output helpers
│   ├── registry_parser.py      # Local project-registry.md parser for reconciliation
│   ├── notion_client.py        # Raw Notion API client
│   ├── notion_export.py        # Write audit results to Notion pages
│   ├── notion_sync.py          # Two-way Notion sync with history versioning
│   ├── notion_dashboard.py     # Notion dashboard page builder
│   ├── notion_registry.py      # Notion registry bidirectional mapping
│   └── analyzers/
│       ├── base.py             # BaseAnalyzer abstract class
│       ├── __init__.py         # ALL_ANALYZERS list + run_all_analyzers()
│       ├── readme.py           # README quality scoring
│       ├── structure.py        # Project structure, config files, .gitignore
│       ├── code_quality.py     # Entry points, TODO density, type hints, commit quality
│       ├── testing.py          # Test presence, framework detection, test file count
│       ├── cicd.py             # GitHub Actions, CI configs, build scripts
│       ├── dependencies.py     # Lockfile presence, manifest detection, dep count
│       ├── activity.py         # Commit recency and frequency via GitHub API
│       ├── completeness.py     # DocumentationAnalyzer + BuildReadinessAnalyzer
│       ├── community_profile.py # LICENSE, CONTRIBUTING, issue templates
│       ├── interest.py         # Tech novelty, project ambition, burst activity
│       └── security.py         # Hardcoded secrets, exposed env files, risky configs
├── tests/                      # 249 tests; mirrors src/ layout
│   └── fixtures/               # Small repo-like directory trees for analyzer tests
├── config/                     # Scoring profile YAML files (lightweight, comprehensive, ci)
├── output/                     # All generated reports land here (gitignored)
│   └── .cache/                 # Disk-cached GitHub API responses (gitignored)
├── scripts/                    # One-off automation scripts
├── docs/                       # Architecture and initiative docs
├── requirements.txt
├── pyproject.toml
├── Makefile
└── .env.example
```

---

## Analyzer Pipeline

### Entry Point

`run_all_analyzers()` in `src/analyzers/__init__.py` iterates over the `ALL_ANALYZERS` list and calls each analyzer's `analyze()` method:

```python
def run_all_analyzers(
    repo_path: Path,
    metadata: RepoMetadata,
    github_client: GitHubClient | None = None,
) -> list[AnalyzerResult]:
```

If an analyzer raises an exception it is caught, logged at `WARNING` level, and a zero-score `AnalyzerResult` with a `"Analysis failed: {error}"` finding is substituted. This ensures a single malformed repo never aborts the full portfolio audit.

### BaseAnalyzer Interface

Every analyzer extends `src/analyzers/base.py::BaseAnalyzer`:

```python
class BaseAnalyzer(ABC):
    name: str    # dimension key, e.g. "readme"
    weight: float

    @abstractmethod
    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult: ...

    def _result(self, score: float, findings: list[str], details: dict | None = None) -> AnalyzerResult:
        """Clamps score to [0.0, 1.0] and wraps in AnalyzerResult."""
```

Analyzers that need live GitHub API data (e.g., `ActivityAnalyzer` for commit frequency) accept the optional `github_client` parameter. File-only analyzers ignore it.

### The 12 Analyzers

| Dimension | Module | What it measures |
|-----------|--------|-----------------|
| `readme` | `readme.py` | Presence, description length, install/usage sections, code examples, badges |
| `structure` | `structure.py` | `.gitignore`, `src/` or language-standard layout, config file, LICENSE, directory depth |
| `code_quality` | `code_quality.py` | Entry point, TODO/FIXME density, type definitions, vendored files, commit message quality |
| `testing` | `testing.py` | Test directories/files, framework config, test file count |
| `cicd` | `cicd.py` | `.github/workflows/`, alternative CI configs, Makefile/build scripts |
| `dependencies` | `dependencies.py` | Lockfile presence, dependency manifest, dep count reasonableness |
| `activity` | `activity.py` | Recency of last push, total commit count, commit activity last 3 months, archived flag |
| `documentation` | `completeness.py` | `docs/` directory, CHANGELOG, CONTRIBUTING, inline comment density |
| `build_readiness` | `completeness.py` | Dockerfile, Makefile, `.env.example`, deployment config files |
| `community_profile` | `community_profile.py` | LICENSE, CONTRIBUTING, issue/PR templates, code of conduct |
| `interest` | `interest.py` | Tech novelty, project ambition signals, commit burst activity, stars/forks |
| `security` | `security.py` | Hardcoded secrets patterns, exposed `.env` files, overly-permissive configs |

---

## Scoring Model

### Completeness Score

`src/scorer.py::score_repo()` computes a weighted average of the 10 completeness dimensions (all except `interest` and `security`):

```python
WEIGHTS: dict[str, float] = {
    "readme": 0.12,
    "structure": 0.10,
    "code_quality": 0.15,
    "testing": 0.18,
    "cicd": 0.10,
    "dependencies": 0.08,
    "activity": 0.15,
    "documentation": 0.02,
    "build_readiness": 0.07,
    "community_profile": 0.03,
}
```

Testing and code quality carry the most weight (0.18 and 0.15). Documentation and community profile are intentionally light (0.02 and 0.03) to avoid penalising exploratory projects.

**Fork override:** For forked repos, the `activity` weight is reduced to `0.05` and the saved weight redistributed proportionally across remaining dimensions. Forks rarely have independent commit history so raw activity is not a meaningful signal.

### Interest Score

`InterestAnalyzer` produces an independent score on the same 0.0–1.0 scale, covering tech novelty, project ambition signals (domain complexity, unusual languages), and burst commit activity. It is not mixed into the completeness score — both axes appear side-by-side in reports.

A portfolio-relative novelty adjustment reduces the interest score for languages the user already uses heavily (≥30% of their portfolio), so the 15th Python CLI project scores lower for novelty than the first Zig project.

### Letter Grades

```
A  ≥ 0.80
B  ≥ 0.70
C  ≥ 0.55
D  ≥ 0.35
F  < 0.35
```

Both the completeness score and the interest score receive independent letter grades.

### Completeness Tiers

| Tier | Score Range | Meaning |
|------|-------------|---------|
| shipped | ≥ 0.75 | Production-ready or clearly complete |
| functional | 0.55 – 0.74 | Works, but missing tests or CI |
| wip | 0.35 – 0.54 | Active development, partially built |
| skeleton | 0.15 – 0.34 | Scaffolded, barely started |
| abandoned | < 0.15 | No meaningful content or no recent activity |

**Override rules:**
- Archived repos with score > 0.50 are capped at `functional`.
- Repos with last push > 2 years ago are capped at `wip` and flagged `stale-2yr`.
- Repos with no meaningful files beyond a README are forced to `skeleton` and flagged `readme-only`.

### Portfolio Health Grade

`compute_portfolio_grade()` adjusts the raw average score with bonuses and penalties:

- **Language diversity bonus:** up to +0.10 for portfolios spanning 4+ languages.
- **Shipped ratio bonus:** +0.05 or +0.10 when > 30% or > 50% of repos are `shipped`.
- **Abandonment penalty:** -0.05 or -0.10 when > 40% or > 60% of repos are `skeleton`/`abandoned`.
- **Badge density bonus:** +0.05 when average badges per repo > 3.

---

## Output Formats

### JSON Report

`output/audit-report-{username}-{date}.json` — full `AuditReport` serialized via `.to_dict()`. Contains all `RepoAudit` objects with per-dimension scores, findings, details, flags, badges, and both axis grades. Machine-readable; used by external tools and PCC import.

### Markdown Report

`output/audit-report-{username}-{date}.md` — human-readable summary with:
- Portfolio summary table: total repos, tier distribution, average scores, portfolio grade.
- Tier-grouped sections (shipped → abandoned) with score, grade, and flags per repo.
- Per-repo detail blocks with dimension breakdown and key findings.
- Registry reconciliation section (if `--registry` flag used).
- Action items: highest-leverage improvement suggestions across the portfolio.

### Excel Dashboard

`output/dashboard-{username}-{date}.xlsx` — analyst workbook generated by `src/excel_export.py`.

The workbook now has two render modes:
- `template` (default): hydrates a committed workbook template and preserves template-owned Excel features.
- `standard`: fallback fully code-generated workbook path for CI, debugging, and template-free environments.

Python owns the workbook facts, not the dashboard behavior:
- hidden `Data_*` sheets and stable Excel tables
- named ranges for top-level workbook KPIs
- table range updates and visible-sheet data hydration

The committed workbook template owns the native Excel experience:
- pivot tables
- slicers
- native sparkline groups
- print and executive formatting
- other dashboard objects that are fragile to build directly in Python

Current visible workbook personas:
- Analyst: `Dashboard`, `Portfolio Explorer`, `By Lens`, `By Collection`, `Trend Summary`
- Operator: `Review Queue`, `Campaigns`, `Writeback Audit`, `Governance Controls`, `Governance Audit`
- Executive: `Executive Summary`, `Print Pack`

Important hidden workbook tables:
- `Data_TrendMatrix`: per-repo recent score history for native sparkline bindings
- `Data_PortfolioHistory`: portfolio-wide historical rollups and drift counts
- `Data_Rollups`: profile, collection, and lens summaries for workbook pivots and executive views
- `Data_ReviewTargets`: recurring-review queue and prioritization inputs

Workbook ranking and history views must always derive from the full filtered portfolio baseline, even during targeted or incremental reruns.

### HTML Dashboard

`output/dashboard-{username}-{date}.html` — self-contained single-file interactive dashboard (`src/web_export.py`) with filterable/sortable repo table and embedded tech radar SVG. No server required; opens directly in a browser.

---

## Caching

### GitHub API Response Cache

`src/cache.py::ResponseCache` caches all GitHub REST API GET responses to `output/.cache/` as JSON files keyed by URL. Cache entries expire after 1 hour. This prevents redundant API calls during incremental re-audits and avoids rate limit exhaustion on large portfolios (100+ repos, each requiring 3-5 API calls).

The cache is bypassed automatically for endpoints that return 202 (GitHub is still computing stats) — these are retried with exponential backoff (2s, 4s, 8s) before falling back to a zero score.

### Clone Workspace Lifecycle

Repos are shallow-cloned (`git clone --depth 1`) to a temporary directory under `/tmp/audit-repos/` (or `$TMPDIR/audit-repos/`). Each repo is cloned to its own subdirectory named `{username}_{repo_name}`. After all analyzers have run against a repo the clone is immediately removed. The temp directory is cleaned up on process exit even if the audit fails, via a `try/finally` block in `cloner.py`.

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| GitHub API client | Raw `requests` calls | Avoids PyGithub/ghapi dependency; REST v3 is stable and sufficient |
| Clone strategy | `--depth 1` (shallow) | Only current file state matters; full history would be ~10x slower |
| Commit history | GitHub API stats endpoints | Faster than parsing local git log; contributor + frequency data in one call |
| Error isolation | Per-analyzer try/except | A malformed repo should never abort the full 100-repo portfolio run |
| Output primary format | JSON | Machine-readable; feeds PCC import, Notion sync, review orchestration, and Excel generation |
| Credentials | Environment variables only | Never passed as CLI args; never logged |
| Excel architecture | Template-assisted `openpyxl` hydration | Preserves native workbook objects while keeping Python focused on facts and tables |
| External dependencies | Minimal (`requests`, `python-dateutil`, `openpyxl`, `radon`, `rich`, `anthropic`) | Keeps installation lightweight; no analysis frameworks |
