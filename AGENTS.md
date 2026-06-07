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

The audit tool, portfolio-truth layer, risk/security overlay, Action Sync proposal
lane, and local `audit serve`/desktop-consumer surfaces are active. The public
remote is `canonical`; `origin` remains a stale private archive and should not be
used for PRs. Do not trust hardcoded status or test-count claims in handoff text:
rerun the local gates and inspect `output/portfolio-truth-latest.json` for the
current Portfolio OS state.

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
python -m src.cli --portfolio-truth --portfolio-truth-include-security <github-username>  # demo truth + security overlay
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

For Portfolio OS demo readiness, refresh `portfolio-truth-latest.json` with
`--portfolio-truth-include-security`, refresh `audit triage --control-center`,
then launch PortfolioCommandCenter with `pnpm demo:desktop`. Current proof
points: 129 projects, 63 open high/critical Dependabot-alert repos, and Weekly
Digest says to start with codexkit. After demo readiness is settled, continue
with the highest-signal live queue item from the current control-center output
rather than reviving old roadmap counts.

<!-- portfolio-context:end -->
