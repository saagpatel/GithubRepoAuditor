# GitHub Repo Auditor — Implementation Roadmap

## Architecture

### System Overview
```
[CLI Entry] → [GitHub API Client] → [Repo Fetcher (clone)] → [Analyzer Engine] → [Report Generator]
                    ↓                        ↓                       ↓                     ↓
              [Rate Limiter]          [/tmp/audit-repos/]      [Per-Repo Scores]     [output/*.json + *.md]
```

**Flow:**
1. CLI accepts username + optional token
2. GitHub API fetches all repos (paginated, handles 100+ repos)
3. Each repo is shallow-cloned to a temp directory
4. Analyzer engine runs 10+ dimension checks per repo
5. Results aggregated into JSON + Markdown report
6. Temp clones cleaned up

### File Structure
```
github-repo-auditor/
├── src/
│   ├── __init__.py
│   ├── cli.py                # argparse entry point
│   ├── github_client.py      # API calls: list repos, get commit stats, get languages
│   ├── cloner.py             # Shallow clone + cleanup
│   ├── analyzers/
│   │   ├── __init__.py
│   │   ├── base.py           # BaseAnalyzer abstract class
│   │   ├── readme.py         # README quality scoring
│   │   ├── structure.py      # Project structure analysis
│   │   ├── code_quality.py   # TODO/FIXME counts, entry points, build configs
│   │   ├── testing.py        # Test presence, framework detection
│   │   ├── cicd.py           # GitHub Actions / CI detection
│   │   ├── dependencies.py   # Lockfile detection, staleness signals
│   │   ├── activity.py       # Commit recency, frequency (via API)
│   │   └── completeness.py   # Overall completeness heuristic
│   ├── scorer.py             # Aggregates analyzer results into per-repo score
│   └── reporter.py           # Generates JSON + Markdown output
├── output/                   # Generated reports land here
├── requirements.txt
├── CLAUDE.md
├── IMPLEMENTATION-ROADMAP.md
└── README.md
```

### Data Model

No database. All data flows through Python dataclasses in memory and writes to JSON.

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class RepoMetadata:
    name: str
    full_name: str
    description: Optional[str]
    language: Optional[str]
    languages: dict[str, int]          # language -> bytes
    private: bool
    fork: bool
    archived: bool
    created_at: datetime
    updated_at: datetime
    pushed_at: datetime
    default_branch: str
    stars: int
    forks: int
    open_issues: int
    size_kb: int
    html_url: str
    clone_url: str
    topics: list[str]

@dataclass
class AnalyzerResult:
    dimension: str                      # e.g., "readme", "testing", "structure"
    score: float                        # 0.0 – 1.0
    max_score: float                    # always 1.0
    findings: list[str]                 # human-readable notes
    details: dict                       # dimension-specific structured data

@dataclass
class RepoAudit:
    metadata: RepoMetadata
    analyzer_results: list[AnalyzerResult]
    overall_score: float                # weighted composite 0.0 – 1.0
    completeness_tier: str              # "shipped", "functional", "wip", "skeleton", "abandoned"
    flags: list[str]                    # e.g., ["no-readme", "no-tests", "stale-2yr"]

@dataclass
class AuditReport:
    username: str
    generated_at: datetime
    total_repos: int
    repos_audited: int                  # excludes forks if --skip-forks
    tier_distribution: dict[str, int]   # tier -> count
    average_score: float
    audits: list[RepoAudit]
```

### API Contracts

**GitHub REST API v3:**

| Endpoint | Method | Auth | Rate Limit | Purpose |
|----------|--------|------|------------|---------|
| `/users/{username}/repos` | GET | Token (optional) | 60/hr unauth, 5000/hr auth | List all public repos |
| `/user/repos` | GET | Token (required) | 5000/hr | List all repos including private |
| `/repos/{owner}/{repo}/languages` | GET | Token (optional) | 5000/hr | Language breakdown by bytes |
| `/repos/{owner}/{repo}/commits` | GET | Token (optional) | 5000/hr | Recent commit activity |
| `/repos/{owner}/{repo}/stats/commit_activity` | GET | Token (optional) | 5000/hr | Weekly commit counts (last year) |
| `/repos/{owner}/{repo}/stats/contributors` | GET | Token (optional) | 5000/hr | Contributor commit counts |
| `/repos/{owner}/{repo}/topics` | GET | Token (optional) | 5000/hr | Repo topics |

**Pagination:** All list endpoints use `Link` header with `rel="next"`. Fetch pages until no `next` link.

**Auth header:** `Authorization: token {GITHUB_TOKEN}` — read from `GITHUB_TOKEN` env var.

**Rate limit handling:** Check `X-RateLimit-Remaining` header. If < 10, sleep until `X-RateLimit-Reset` timestamp.

### Dependencies
```bash
pip install requests python-dateutil
```

That's it. Two dependencies. Everything else is stdlib.

---

## Scope Boundaries

**In scope:**
- Fetch all repos (public + private with token) for a given GitHub username
- Shallow clone each repo and run local file analysis
- Score across 10 dimensions (see analyzer details below)
- Classify each repo into a completeness tier
- Generate JSON report (machine-readable, PCC-compatible)
- Generate Markdown summary report (human-readable)
- Handle 100+ repos gracefully with progress output
- Skip forks optionally via `--skip-forks` flag

**Out of scope:**
- Web UI or dashboard (output is files only)
- Running actual test suites or build commands
- Dependency vulnerability scanning (just detect presence of lockfiles)
- GitHub Actions run history analysis
- Cross-repo dependency detection
- Organization repos (user repos only)

**Deferred:**
- Integration with project-registry.md reconciliation (Phase 2)
- PCC import format generation (Phase 2)
- Historical trend tracking across multiple audit runs (future)

## Security & Credentials
- GitHub token read from `GITHUB_TOKEN` environment variable — never passed as CLI arg, never logged
- Token is optional for public-only audits, required for private repos
- Cloned repos are written to a temp directory and cleaned up after analysis
- No data leaves the machine — all analysis is local

---

## Analyzer Dimension Specifications

Each analyzer scores 0.0–1.0. The overall score is a weighted average.

### 1. README Quality (`readme.py`) — Weight: 15%
| Check | Points | Detection |
|-------|--------|-----------|
| README exists | 0.2 | `README.md` or `README` or `README.rst` in root |
| Has project description (>50 chars first section) | 0.2 | Parse first heading + paragraph |
| Has installation/setup instructions | 0.2 | Look for headings containing "install", "setup", "getting started", "usage" |
| Has usage examples or screenshots | 0.2 | Look for code blocks or image references |
| Length > 500 chars | 0.1 | Character count |
| Has badges | 0.1 | `![` patterns in first 10 lines |

### 2. Project Structure (`structure.py`) — Weight: 10%
| Check | Points | Detection |
|-------|--------|-----------|
| Has `.gitignore` | 0.2 | File exists |
| Has `src/` or `lib/` or language-standard structure | 0.3 | Directory detection based on primary language |
| Has config file (package.json, Cargo.toml, pyproject.toml, etc.) | 0.3 | File exists by known names |
| Has LICENSE file | 0.1 | `LICENSE` or `LICENSE.md` in root |
| Not a flat dump (>1 directory depth) | 0.1 | Directory tree depth analysis |

### 3. Code Quality Signals (`code_quality.py`) — Weight: 15%
| Check | Points | Detection |
|-------|--------|-----------|
| Has identifiable entry point | 0.3 | `main.py`, `index.ts`, `src/main.rs`, `main.go`, `App.tsx`, etc. |
| TODO/FIXME density < 5 per 1000 LOC | 0.2 | Grep + LOC count |
| Has type definitions (if applicable) | 0.2 | `.ts` files, Python type hints, Rust types |
| No large generated/vendored files | 0.15 | Detect `vendor/`, `node_modules/` committed, files >1MB |
| Has meaningful commit messages (last 10) | 0.15 | Via API: check messages aren't all "update" or "fix" |

### 4. Testing (`testing.py`) — Weight: 15%
| Check | Points | Detection |
|-------|--------|-----------|
| Test directory or test files exist | 0.4 | `test/`, `tests/`, `__tests__/`, `*_test.*`, `*_spec.*`, `test_*.*` |
| Test framework configured | 0.3 | jest in package.json, pytest in pyproject.toml, etc. |
| Test count > 0 (heuristic) | 0.3 | Count files matching test patterns |

### 5. CI/CD (`cicd.py`) — Weight: 10%
| Check | Points | Detection |
|-------|--------|-----------|
| `.github/workflows/` exists with YAML files | 0.5 | Directory + file check |
| Alternative CI config (`.travis.yml`, `Jenkinsfile`, `.circleci/`, `Dockerfile`) | 0.3 | File exists |
| Has build script in package.json / Makefile | 0.2 | Parse for "build", "test" scripts |

### 6. Dependency Management (`dependencies.py`) — Weight: 10%
| Check | Points | Detection |
|-------|--------|-----------|
| Has lockfile (`package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock`, `Pipfile.lock`) | 0.4 | File exists |
| Has dependency manifest (package.json, requirements.txt, Cargo.toml, go.mod) | 0.4 | File exists |
| Dependencies count is reasonable (not 0, not 500+) | 0.2 | Parse manifest for dep count |

### 7. Activity & Recency (`activity.py`) — Weight: 15%
| Check | Points | Detection |
|-------|--------|-----------|
| Last push within 6 months | 0.3 | `pushed_at` from API |
| Last push within 1 year | 0.2 | `pushed_at` from API (if >6mo, partial credit) |
| More than 10 commits total | 0.2 | Contributor stats API |
| Commits in last 3 months | 0.2 | Commit activity API |
| Not archived | 0.1 | `archived` field from API |

### 8. Documentation Beyond README (`completeness.py`) — Weight: 5%
| Check | Points | Detection |
|-------|--------|-----------|
| Has `docs/` directory or wiki-style files | 0.3 | Directory check |
| Has CHANGELOG or HISTORY file | 0.3 | File exists |
| Has CONTRIBUTING guide | 0.2 | File exists |
| Has inline code comments (sampling) | 0.2 | Sample 5 largest files, check comment density |

### 9. Build/Run Readiness (`completeness.py`) — Weight: 5%
| Check | Points | Detection |
|-------|--------|-----------|
| Has Dockerfile or docker-compose | 0.3 | File exists |
| Has Makefile or build script | 0.3 | File exists |
| Has environment example (.env.example, .env.sample) | 0.2 | File exists |
| Has deployment config (Vercel, Netlify, fly.toml, etc.) | 0.2 | File exists |

---

## Completeness Tier Classification

Based on overall weighted score:

| Tier | Score Range | Description |
|------|-------------|-------------|
| **Shipped** | 0.75 – 1.0 | Production-ready or clearly complete. README, tests, CI, recent activity. |
| **Functional** | 0.55 – 0.74 | Works but rough edges. Missing tests or CI. Has clear entry point. |
| **WIP** | 0.35 – 0.54 | Active development, partially built. Some structure, some code, incomplete. |
| **Skeleton** | 0.15 – 0.34 | Scaffolded but barely started. Boilerplate only. |
| **Abandoned** | 0.0 – 0.14 | No meaningful content, no recent activity, or just a README. |

**Override rules:**
- If `archived == true` and score > 0.5 → cap tier at "Functional" (archived = not actively shipped)
- If `fork == true` → add flag `"forked"`, reduce activity weight to 5%
- If last push > 2 years ago → add flag `"stale-2yr"`, cap tier at "WIP" regardless of score
- If repo has 0 files beyond README → force tier to "Skeleton"

---

## Phase 0: Foundation (Day 1)

**Objective:** Working CLI that fetches repos from GitHub API, clones them, and outputs raw metadata JSON.

**Tasks:**
1. Scaffold project structure per file tree above — **Acceptance:** All directories and `__init__.py` files exist
2. Implement `github_client.py` — list repos with pagination, rate limit handling — **Acceptance:** `python -m src.cli saagpatel` prints repo names to stdout
3. Implement `cloner.py` — shallow clone to temp dir, cleanup after — **Acceptance:** Repos appear in `/tmp/audit-repos/`, are removed after script exits
4. Implement `cli.py` with argparse — **Acceptance:** `python -m src.cli --help` shows usage; `python -m src.cli saagpatel --token $GITHUB_TOKEN` runs end-to-end
5. Write `RepoMetadata` dataclass and populate from API response — **Acceptance:** `output/raw_metadata.json` contains all repos with all fields populated

**Verification checklist:**
- [ ] `python -m src.cli saagpatel` → prints list of all public repos
- [ ] `python -m src.cli saagpatel --token $GITHUB_TOKEN` → includes private repos
- [ ] `output/raw_metadata.json` exists and is valid JSON with all repos
- [ ] No repos left in temp directory after script completes
- [ ] Rate limit handling works (check `X-RateLimit-Remaining` logged)

**Risks:**
- GitHub stats endpoints return 202 (computing) on first call: Retry with exponential backoff (3 attempts, 2s/4s/8s)
- Rate limit hit with 100+ repos: Implement sleep-until-reset using `X-RateLimit-Reset` header

---

## Phase 1: Analyzer Engine (Day 1–2)

**Objective:** All 9 analyzer dimensions implemented, producing per-repo scores.

**Tasks:**
1. Implement `BaseAnalyzer` abstract class with `analyze(repo_path: Path, metadata: RepoMetadata) -> AnalyzerResult` — **Acceptance:** Interface defined, type-checked
2. Implement all 9 analyzers per dimension specs above — **Acceptance:** Each returns `AnalyzerResult` with score, findings, details
3. Implement `scorer.py` — weighted aggregation + tier classification with override rules — **Acceptance:** `RepoAudit` objects have `overall_score` and `completeness_tier` populated
4. Wire analyzers into CLI pipeline: fetch → clone → analyze → score — **Acceptance:** `python -m src.cli saagpatel` produces scored results for all repos
5. Add `--verbose` flag that prints per-dimension scores per repo — **Acceptance:** Verbose output shows all 9 dimension scores per repo

**Verification checklist:**
- [ ] Run against 3 repos of varying quality → scores feel intuitive (high for complete, low for skeletons)
- [ ] Override rules work: archived repos capped, stale repos flagged
- [ ] `--verbose` shows per-dimension breakdown
- [ ] No crashes on empty repos, repos with no code, or repos with unusual structures

**Risks:**
- Analyzer crashes on unexpected file structures: Wrap each analyzer in try/except, return score 0.0 with finding "analysis failed: {error}"
- Large repos slow down analysis: Set max file scan limit (500 files per repo, skip binary files)

---

## Phase 2: Report Generation (Day 2–3)

**Objective:** Full JSON + Markdown reports with summary statistics, tier distribution, and per-repo breakdowns.

**Tasks:**
1. Implement JSON report output — **Acceptance:** `output/audit-report-{username}-{date}.json` matches `AuditReport` schema exactly
2. Implement Markdown report with:
   - Summary table (total repos, tier distribution, average score)
   - Tier-grouped repo lists with scores and key flags
   - Per-repo detail sections (expandable in Markdown viewers)
   — **Acceptance:** `output/audit-report-{username}-{date}.md` renders cleanly in GitHub/VS Code preview
3. Add `--skip-forks` flag — **Acceptance:** Fork repos excluded from analysis and report when flag set
4. Add `--output-dir` flag — **Acceptance:** Reports written to specified directory
5. Add progress bar using stderr prints — **Acceptance:** Shows `[12/47] Analyzing repo-name...` during run
6. Add PCC-compatible JSON export — flat array of objects with fields matching PCC project schema (name, status, score, url, last_activity, tier, flags) — **Acceptance:** `output/pcc-import-{username}-{date}.json` is importable into PCC

**Verification checklist:**
- [ ] JSON report validates against `AuditReport` dataclass
- [ ] Markdown report renders with proper tables and formatting
- [ ] `--skip-forks` correctly excludes forked repos
- [ ] `--output-dir /custom/path` writes reports there
- [ ] Progress output shows on stderr (not mixed with stdout)
- [ ] PCC import file has flat structure ready for dashboard import

**Risks:**
- Markdown table formatting breaks with long repo names: Truncate names to 40 chars in tables
- JSON serialization fails on datetime objects: Use `.isoformat()` for all datetimes

---

## Phase 3: Polish & Reconciliation (Day 3)

**Objective:** Cross-reference with local project-registry.md, add summary stats, handle edge cases.

**Tasks:**
1. Add `--registry` flag accepting path to project-registry.md — **Acceptance:** Report includes "On GitHub but not in registry" and "In registry but not on GitHub" sections
2. Registry parser: extract project names and statuses from markdown — **Acceptance:** Parses the registry format used at `~/Projects/project-registry.md`
3. Add summary statistics to report: most active repos, most neglected, highest/lowest scored, language distribution — **Acceptance:** Summary section in Markdown report has all stats
4. Handle edge cases: empty repos, repos with only a README, repos with >10k files, binary-only repos — **Acceptance:** No crashes, appropriate tier assignments
5. Write README.md for the auditor tool itself — **Acceptance:** Complete with usage, examples, output format docs

**Verification checklist:**
- [ ] Full audit run against `saagpatel` completes without errors
- [ ] Registry reconciliation correctly identifies gaps in both directions
- [ ] Summary statistics are accurate (spot-check 3 repos manually)
- [ ] README documents all CLI flags and output formats
- [ ] Tool audits itself and scores > 0.6

**Risks:**
- Registry format varies: Build a lenient parser that handles common markdown table and list formats
- Too many API calls for large accounts: Cache API responses to `output/.cache/` with 1-hour TTL
