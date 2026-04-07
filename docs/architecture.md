# Architecture

GitHub Repo Auditor is a Python CLI tool that audits a GitHub user's entire repository portfolio. It fetches repo metadata from the GitHub REST API, shallow-clones each repo, runs 12 analysis dimensions over the local files, scores them on a dual-axis model (completeness + interest), and writes structured output in JSON, Markdown, Excel, and HTML formats.

Before normal runs start, the CLI now performs a shared preflight. That diagnostics layer validates config shape, GitHub and Notion readiness, workbook/template availability, output-path writability, and whether baseline-dependent paths such as targeted or incremental reruns have the history they need. The dedicated `--doctor` mode runs that broader diagnostics set without auditing repos and writes a machine-readable artifact to `output/diagnostics-<username>-<date>.json`.

Targeted and incremental reruns now rely on a shared baseline contract. A prior report is only considered safe for partial reruns if it was produced under a compatible audit-affecting context: username, scoring profile, skip-forks, skip-archived, scorecard, security-offline, and the filtered portfolio baseline used for scoring. Legacy reports remain readable for viewing and regeneration, but partial reruns fail closed until a fresh full baseline is produced.

The CLI also now has a read-only `--control-center` path. It loads the latest report + warehouse state, normalizes review state when older reports are missing it, and builds one shared triage queue for setup blockers, review work, campaign drift, and governance readiness without running a new audit.

Watch mode now uses that same baseline contract in live execution. `--watch-strategy adaptive|incremental|full` controls how each cycle is chosen, and the resulting watch decision is recorded into `watch_state` so control-center, workbook, Markdown, and HTML surfaces can explain why the next run should be full or incremental.

The documented primary command is now `audit`, exposed through the package console script. `python -m src` remains a supported fallback for environments that prefer module execution.

## Typical Invocation

```bash
# Audit all public repos for a user
audit saagpatel

# Audit with private repos and Notion sync
audit saagpatel --token $GITHUB_TOKEN --notion

# Incremental re-audit of recently-changed repos only
audit saagpatel --incremental

# Audit two specific repos with AI narrative
audit saagpatel --repos my-app,my-lib --ai-narrative
```

---

## Project Structure

```
github-repo-auditor/
├── src/
│   ├── cli.py                  # argparse entry point — audit, doctor, control-center, and operator flows
│   ├── github_client.py        # REST API calls: list repos, commit stats, languages, releases
│   ├── graphql_client.py       # GraphQL bulk queries for batch metadata fetching
│   ├── cloner.py               # Shallow clone (depth=1) to temp dir + cleanup
│   ├── models.py               # RepoMetadata, AnalyzerResult, RepoAudit, AuditReport dataclasses
│   ├── diagnostics.py          # Shared setup/preflight checks + doctor artifact generation
│   ├── operator_control_center.py # Shared operator triage snapshot + control-center artifacts
│   ├── scorer.py               # Weighted aggregation, tier classification, grade computation
│   ├── reporter.py             # JSON + Markdown report writers
│   ├── cache.py                # ResponseCache: disk-backed GitHub API response cache (1hr TTL)
│   ├── history.py              # Audit history persistence across runs
│   ├── diff.py                 # Score delta computation between two audit runs
│   ├── badges.py               # Badge award logic and badge catalog
│   ├── badge_export.py         # Shields.io badge URL generation + optional Gist upload
│   ├── excel_export.py         # Standard + template-backed Excel workbook export
│   ├── workbook_gate.py        # Canonical workbook release gate: sample artifacts + invariant checks
│   ├── excel_styles.py         # Excel design system: colors, fonts, named styles
│   ├── excel_template.py       # Template workbook helpers + native sparkline injection
│   ├── web_export.py           # Interactive HTML dashboard generation
│   ├── narrative.py            # AI-generated plain-English repo summaries (Anthropic API)
│   ├── similarity.py           # TF-IDF cross-repo similarity detection
│   ├── archive_candidates.py   # Identify + batch-archive abandoned repos via GitHub API
│   ├── quick_wins.py           # Per-repo lowest-effort improvement suggestions
│   ├── readme_suggestions.py   # README improvement diff generation
│   ├── portfolio_readme.py     # GitHub profile README generator from audit data
│   ├── libyears.py             # Library-years dependency staleness metric
│   ├── sparkline.py            # Unicode sparklines for terminal commit activity display
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
├── tests/                      # Mirrors src/ layout
│   └── fixtures/               # Small repo-like directory trees for analyzer tests
├── config/                     # Scoring profile YAML files (lightweight, comprehensive, ci)
├── output/                     # All generated reports land here (gitignored)
│   └── .cache/                 # Disk-cached GitHub API responses (gitignored)
├── scripts/                    # One-off automation scripts
├── docs/                       # Architecture and initiative docs
├── requirements.txt            # Compatibility mirror of runtime deps in pyproject.toml
├── pyproject.toml             # Canonical package metadata + dependencies + console script
├── Makefile                   # Operator/dev entrypoints: install, doctor, audit, control-center, workbook-gate, test
└── .env.example               # Environment template for GitHub, Notion, workbook, and optional AI usage
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

`output/audit-dashboard-{username}-{date}.xlsx` — workbook generated by `src/excel_export.py`.

The workbook now has two modes:
- `standard`: stable code-generated workbook path, the CLI default, used by automation, and recommended for broad Excel compatibility.
- `template`: hydrates the committed workbook template and preserves template-owned workbook structure.

Important workbook facts:
- Hidden `Data_*` sheets remain the source of truth.
- Visible user-facing sheets now use plain filtered ranges, while hidden `Data_*` sheets keep structured tables for workbook bindings and downstream safety.
- New workbook contract tables include `tblTrendMatrix`, `tblPortfolioHistory`, `tblRollups`, and `tblReviewTargets`.
- Operator KPI bindings are exposed via workbook named ranges rather than workbook-only calculations.
- Workbook ranking and trend views must always derive from the full filtered portfolio baseline, even during targeted or incremental reruns.
- Template mode is validated during preflight so missing or corrupt workbook assets fail before a run starts.
- The current phase does not change workbook ownership boundaries: one workbook artifact, `standard` as the operational mode, filter-based visible sheets, and additive-only changes to hidden workbook data contracts.

## Install and Daily Use

The intended operator path is now:

1. `make install`
2. Copy `.env.example` to `.env`
3. Copy `config/examples/audit-config.example.yaml` to `audit-config.yaml`
4. Add `config/examples/notion-config.example.json` if you plan to use Notion features
5. Run `audit <username> --doctor`
6. Run `audit <username>`
7. Run `audit <username> --control-center`

### Campaign and Governance Lifecycle

Managed campaign work now reconciles against prior managed state rather than assuming every run is a fresh mutation.

- `--campaign-sync-mode reconcile` updates active managed records and closes stale ones.
- `--campaign-sync-mode append-only` leaves stale managed records open and marks them stale.
- `--campaign-sync-mode close-missing` closes previously managed records that are no longer present in the current campaign selection.

The report and warehouse persist per-action lifecycle state, reconciliation outcomes, managed-state drift, rollback preview coverage, and campaign history. Governance remains manual and opt-in, but operator surfaces now preserve approval, result, drift, and rollback coverage data when governance context is present.

Governance in this phase is intentionally limited to the current supported GitHub-administered control family. The finish pass hardens trust and clarity around those controls; it does not expand into rulesets, branch protection, or repo-content mutation.

The diagnostics layer is intentionally shared rather than feature-local:
- normal runs use a lightweight automatic preflight
- `--preflight-mode strict` upgrades warnings into blockers
- `--preflight-mode off` skips automatic preflight
- `--doctor` runs the broader diagnostics set without cloning or auditing repos

Outputs may project the compact `preflight_summary`, but they do not recompute setup logic themselves.

### Operator Control Center

`--control-center` is the CLI-first daily triage front door. It is intentionally read-only and local-authoritative.

- It reads the latest report JSON plus warehouse-backed campaign/governance state.
- It normalizes review state into the shared contract when older reports are missing those fields.
- It builds one ordered operator queue with four lanes:
  - `blocked`
  - `urgent`
  - `ready`
  - `deferred`
- It writes:
  - `operator-control-center-<username>-<date>.json`
  - `operator-control-center-<username>-<date>.md`

The same shared `operator_summary` and `operator_queue` are then projected into Markdown, HTML, Excel, and review-pack surfaces. Those outputs do not maintain separate triage logic.

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
| Output primary format | JSON | Machine-readable; feeds PCC import, Notion sync, and Excel generation |
| Credentials | Environment variables only | Never passed as CLI args; never logged |
| External dependencies | Minimal (`requests`, `python-dateutil`, `openpyxl`, `radon`, `rich`, `anthropic`, `fpdf2`, `pyyaml`) | Keeps installation lightweight while matching current workbook, PDF, and config support |
