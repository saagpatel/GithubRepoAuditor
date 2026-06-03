<!-- portfolio-context:start -->
# Portfolio Context

## What This Project Is

A portfolio audit and operator tool — a "GitHub portfolio operating system" — for
developers with many repositories. It clones every repo on a GitHub account, runs 12
analyzers across completeness and interest dimensions, assigns letter grades, achievement
badges, and dual-axis scores, preserves historical state in SQLite, and generates aligned
JSON / Markdown / HTML / Excel-workbook / control-center surfaces so you can decide what to
finish, fix, or safely ignore. Published on PyPI as `github-repo-auditor`. The day-to-day
operating surfaces are the Excel workbook and the read-only `audit triage --control-center`
queue.

## Current State

Two stable layers ship: the audit tool (Phases 0–27) and the portfolio-truth layer
(Phases 103–108), at schema `0.5.0`. 2209 tests collected, ruff clean, CI + CodeQL green on
`main` (currently `bba2e08`). Active work is **Arc A — context-quality recovery**: the
catalog-completeness flag has been driven to 0 and the weak-context flag is down from 24 to
5 legitimate stragglers. Recent PRs #33–#38 seeded the repo catalog, added a discovery
ignore-list for transient non-project dirs, exempted archived/dormant repos from the context
flag, and fixed three false-negative bugs in the context-quality analyzer. All Arc A work
merges to the `canonical` remote.

## Stack

- Language: Python 3.11+
- GitHub API: REST v3 + GraphQL (raw `requests`)
- Excel: `openpyxl` + committed workbook template; PDF: `fpdf2`
- AI narrative: Anthropic Claude API; complexity analysis: Radon; CLI output: Rich
- Storage: SQLite history warehouse
- `pyproject.toml` is the canonical dependency definition (`requirements.txt` is a synced mirror)

## How To Run

```bash
# install (editable, dev + optional extras)
pip install -e ".[dev,serve,semantic,config]"

# core operator loop
audit run <github-username> --doctor               # preflight diagnostics
audit run <github-username> --html                 # full audit + workbook + dashboard
audit triage <github-username> --control-center    # read-only operator queue
audit report <github-username> --portfolio-truth   # regenerate workspace truth layer
audit serve                                        # local web UI at http://127.0.0.1:8080/

# tests + gates
python3 -m pytest -q -p no:cacheprovider           # full suite
python3 -m ruff check src/ tests/                  # lint
make demo                                          # token-free sample run from fixture
make workbook-gate                                 # workbook invariant check (workbook code only)
```

## Known Risks

- **Dual remote**: push/PR to the `canonical` remote (public), NOT `origin` — `origin` is a
  stale private archive with unrelated history, so PRs against it fail with "no common
  history". Solo repo, so merges land with `gh ... --admin`.
- **The context-quality metric is gameable**: injecting generic-filler context blocks zeros
  the flag while lying about resumability. Only real harvested content counts — this block
  was hand-authored for exactly that reason.
- **Five parallel render surfaces** (Excel workbook, Markdown, HTML, review-pack, handoff)
  carry a parity tax: every new signal must be threaded through all five (the motivation for
  the deferred Arc F renderer simplification).
- **Partial reruns fail closed**: `--repos` / `--incremental` require a compatible full
  baseline; the stored baseline contract rejects mismatched portfolio context rather than
  emitting a misleading partial.
- **Manual workbook signoff**: the final release step is opening the generated `standard`
  workbook in desktop Excel and recording the outcome with `make workbook-signoff`.

## Next Recommended Move

Finish Arc A by clearing the three remaining context flags blocked only by dirty worktrees
(BattleGrid, LegalDocsReview, TabTriage) — land or stash each repo's in-progress work, then
apply the same real-content-only check before injecting any block. After Arc A, the
highest-leverage arc is **Arc B (enrichment-layer risk integration)**: surface the
already-computed risk posture in the Excel workbook, HTML dashboard, and review-pack so all
five render surfaces reach parity — a low-risk renderer extension. Arc C (wire or remove the
six orphaned public functions) is a small, safe cleanup that can ride alongside.

<!-- portfolio-context:end -->
