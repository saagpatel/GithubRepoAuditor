# 2026-05-10 — Arc F Expansion Roadmap

**Status:** Active — Sprint 1 in progress
**Owner:** Solo operator
**Arc:** F (follows Arc D bounded automation and Arc E desktop shell concept)
**Reference window:** 90-day sequencing (≈ 2026-05-10 → 2026-08-10), with longer-horizon backlog

---

## TL;DR

GithubRepoAuditor has matured into a workbook-first portfolio operator with bounded automation behind a trust bar. The next arc of work is **not new analyzers** — it is tightening the loop: faster runs, an interactive UI, a semantic index that makes future AI features cheap, and platform-native data that GitHub now exposes for free. This plan defines four strategic themes, a feature inventory (~30 items), four 90-day sprints with five items each, plus an explicit backlog and deferred list.

The single guiding principle: **every change in Arc F either (a) increases operator velocity per audit run, or (b) lays a foundation that several downstream features will share.**

---

## Why this work, now

1. **The platform caught up.** GitHub's free API surface in 2025-26 now includes SBOM export, Dependabot/CodeQL/Secret-scanning alert reads, GitHub Models inference, repo rulesets, code search, releases, and stargazer timelines. Several of GithubRepoAuditor's existing analyzers can be replaced or augmented with first-party data that's richer and cheaper to obtain.
2. **Trust-bar infrastructure is ready.** Arc D (Phases 119-122) shipped the `automation_eligible` + `baseline risk` + `trusted decision quality` gate. The approval ledger and campaign packet workflow are the right substrate for richer agentic features — proposing actions through the same lane that already exists.
3. **The bottlenecks are known.** Workbook generation is slow on 100+ repos, GitHub fetch is sequential, there is no interactive UI for browsing historical runs, and the CLI has 70+ flags in one flat namespace. Each has a clean fix.
4. **The single-paragraph `--narrative` is the only AI surface.** With Haiku, voyage-code-3 embeddings, and GitHub Models all viable, a single shared semantic index can unlock several features without recurring API spend.

---

## Strategic themes

### Theme 1 — Close the platform-native gap

Move data acquisition from local clones + custom scrapers to GitHub's first-party APIs where they're now strictly better. Free, faster, richer.

### Theme 2 — AI as analyst, not just narrator

Promote AI from a one-paragraph generator to a portfolio analyst: semantic queries, weekly briefings, agentic README drafts that flow through the existing approval lane, and operator-preference memory so suggestions don't become noise.

### Theme 3 — New analytical dimensions

Borrow proven patterns from adjacent tools (OSSF Scorecard, Cortex maturity tiers, DORA-Lite, OpenSauced contributor signals). Each new dimension must be (a) cheap to compute, (b) actionable, and (c) surfaced in both Excel and the control center.

### Theme 4 — Architecture, performance, distribution

Fix the known bottlenecks. Move from "run it overnight" to "rerun during triage." Make the tool installable on a fresh machine in one command. Reduce the CLI's flag-soup problem.

---

## Full feature inventory

Status legend: ✅ in Arc F sprints · 📋 Arc F backlog · ⏸ deferred (with reason)

### Theme 1 — Platform-native

| # | Feature | Status | Sprint |
|---|---|---|---|
| 1.1 | Dependabot + CodeQL + Secret-scanning alerts in `risk_overlay` | ✅ | S1.3 |
| 1.2 | SBOM-based dependency fetching (`--sbom-source github`) | ✅ | S2.3 |
| 1.3 | GitHub Models as alternate `--narrative-provider` | ✅ | S1.2 |
| 1.4 | OSSF Scorecard integration | ✅ | S2.3 (combined with SBOM) |
| 1.5 | Repo rulesets + signing as governance score | 📋 | post-S4 |
| 1.6 | CI health analyzer (workflow run metrics) | 📋 | post-S4 |
| 1.7 | Cross-repo code search (`--cross-repo-search`) | 📋 | post-S4 |
| 1.8 | Webhook daemon (`--serve-webhook`) | ⏸ | Operational complexity outweighs solo-operator value |

### Theme 2 — AI as analyst

| # | Feature | Status | Sprint |
|---|---|---|---|
| 2.1 | Portfolio semantic index (`--semantic-search`, `--ask`) | ✅ | S3.1 |
| 2.2 | Weekly Operator Briefing (`--briefing`) | ✅ | S3.2 |
| 2.3 | Operator preference memory | ✅ | S3.3 |
| 2.4 | Cross-repo duplication detector | 📋 | post-S3 (built on 2.1) |
| 2.5 | Agentic README/description authoring (`--draft-readmes`) | 📋 | post-S4 |
| 2.6 | Planner agent for campaign authoring (`--plan-campaign`) | 📋 | post-S4 |
| 2.7 | Eval-driven scoring tuning (`--tune-scoring-profile`) | 📋 | post-S4 |
| 2.8 | LLM code-quality analyzer per file | ⏸ | Cost vs. signal-add not justified vs. deterministic analyzers |
| 2.9 | Local-first Ollama classification | ⏸ | Defer until API spend is a real constraint |

### Theme 3 — New analytical dimensions

| # | Feature | Status | Sprint |
|---|---|---|---|
| 3.1 | README staleness index | ✅ | S1.4 |
| 3.2 | Release-shipped signal (has-release + age + count) | ✅ | S1.4 |
| 3.3 | Star momentum (30d delta) | 📋 | post-S4 |
| 3.4 | Tiered maturity + Initiative tracker | 📋 | post-S4 |
| 3.5 | DORA-Lite metrics (release cadence, lead-time, change-failure proxy) | 📋 | post-S4 |
| 3.6 | Year-in-review report (`--year-review`) | 📋 | post-S4 |
| 3.7 | Cross-repo context-switching heatmap | 📋 | post-S4 |
| 3.8 | Commit-message hygiene | 📋 | post-S4 |
| 3.9 | Bus-factor / collaborator awareness | 📋 | post-S4 |
| 3.10 | Milestone hygiene | 📋 | post-S4 |
| 3.11 | Auto-topic suggestions via LLM (dry-run) | 📋 | post-S4 |

### Theme 4 — Architecture, performance, distribution

| # | Feature | Status | Sprint |
|---|---|---|---|
| 4.1 | xlsxwriter migration (`constant_memory=True`) | ✅ | S1.1 |
| 4.2 | mutmut pre-release gate on `auto_apply` + `scorer` | ✅ | S1.5 |
| 4.3 | Async fetch layer (`--fetch-workers`, httpx) | ✅ | S2.1 |
| 4.4 | Per-(repo, sha, analyzer) cache in warehouse DB | ✅ | S2.2 |
| 4.5 | `audit serve` — FastAPI + HTMX local web UI | ✅ | S4.1 |
| 4.6 | PyPI publish + `shiv` binary | ✅ | S4.2 |
| 4.7 | CLI subcommand restructure (`audit run/triage/report`) | ✅ | S4.3 |
| 4.8 | structlog + per-phase timings to `run-telemetry.jsonl` | 📋 | post-S4 |
| 4.9 | Plugin architecture via entry-points | 📋 | post-S4 |
| 4.10 | Arc E desktop shell (Tauri 2 + React) | 📋 | post-S4 (after `audit serve` validates which views matter) |
| 4.11 | OpenTelemetry traces | ⏸ | Overkill for solo tool; JSONL telemetry is enough |

---

## 90-day sequencing

Each sprint is ≈ 2 weeks of focused work and ships behind a feature flag where applicable. Sprints are ordered to compound: Sprint 1's xlsxwriter win is immediately felt every run; Sprint 2's cache + async layer make Sprint 3's AI iteration cheap; Sprint 4's UI exposes everything that came before.

### Sprint 1 — Quick performance + platform wins (current)

**Goal:** Within 2 weeks, every full-portfolio run is faster, every report has GHAS data and shipped-release signals, and the auto-apply path is hardened by mutation testing.

#### S1.1 — Excel write-path optimization (openpyxl write_only mode)

- **Decision history:** Initial scope was a full xlsxwriter migration. Inspection of the actual surface (49 excel_*.py modules, 43 import sites, heavy use of `merge_cells`/`conditional_formatting.add`/`add_chart`/`Table`/`DefinedName`, plus `excel_template.py` calling `openpyxl.load_workbook` on a committed template) showed xlsxwriter is not a drop-in: it cannot read existing xlsx files (no `load_workbook`), and `constant_memory=True` forbids the back-reference patterns used in many helpers. Pivoted to openpyxl's own streaming `write_only=True` mode (2026-05-10).
- **Goal:** Reduce peak RAM during workbook generation on 100+ repo runs by switching the from-scratch standard-workbook path to openpyxl's streaming mode where viable, while keeping the template-driven path on regular openpyxl.
- **Constraints to validate first** (write_only mode):
  - `WriteOnlyWorksheet.append(row)` only — no `ws.cell(...)`.
  - `merge_cells`, `conditional_formatting.add`, and inline cell mutation are **not supported** on write-only sheets.
  - Charts can be added at workbook close time, but data must be already written.
  - Workbook-level features (defined names, hyperlinks, tables) still work.
- **Scope (likely phased):**
  1. **Phase 1 — Investigation pass.** Catalog every helper by which write_only-incompatible API it uses. Identify a subset of sheets that are pure tabular `append`-only (good streaming candidates) vs. sheets that genuinely need back-reference features (stay on regular openpyxl).
  2. **Phase 2 — Adapter introduction.** Add a thin `excel_engine` adapter giving each helper a `make_sheet(name, streaming: bool)` factory. Streaming sheets get write_only behavior; non-streaming keep the current pattern. No behavior change at this stage — wire the adapter, default everything to `streaming=False`.
  3. **Phase 3 — Flip streaming on for safe sheets.** Per the Phase-1 catalog, set `streaming=True` for tabular sheets (likely `All Repos`, `Portfolio Explorer`, `Run Changes`, `Historical Intelligence`, possibly `Repo Detail`).
  4. **Phase 4 — Validate.** Benchmark vs. baseline; run snapshot tests; if any sheet's output differs, document or revert.
- **Files likely affected:** `src/excel_export.py`, `src/excel_workbook_helpers.py`, new `src/excel_engine.py`, the helpers for the streaming-eligible sheets only, `pyproject.toml`, `tests/test_excel_*.py`.
- **Tests required:**
  - Existing workbook tests pass unchanged.
  - New benchmark test (gated by `-m benchmark`) timing workbook gen on a 100-repo fixture.
  - Snapshot test confirming streaming-eligible sheets produce identical content (sheet name, row count, key cell values) before and after.
- **Effort (revised):** Medium (3-5 days), split into the four phases above.
- **Exit criteria:** Phase 1 catalog committed; at least one sheet converted to streaming with passing tests; benchmark shows a measurable peak-RAM drop on the 100-repo fixture; `--excel-engine` legacy escape hatch documented.
- **Stop condition:** If Phase 1 reveals that fewer than 3 sheets are streaming-eligible, S1.1 ships only the investigation report + adapter scaffolding, and the bulk RAM optimization moves to Sprint 2 with a different approach (likely: profile to find the real bottleneck, which may not be openpyxl at all).

- **Phase 1 result (2026-05-10):** Stop condition triggered. The streaming catalog in `docs/plans/2026-05-10-s1.1-phase1-streaming-catalog.md` confirms:
  1. `write_only=True` is a workbook-level flag — `WriteOnlyWorksheet` and regular `Worksheet` cannot coexist in one `Workbook`. The pipeline passes a single shared `wb` through 49 helper modules, so splitting is impractical.
  2. **All 20 visible sheets** use at least one write-only-incompatible API (`ws.cell()`, `merge_cells`, `add_table`, `data_validation`, or `freeze_panes` post-write). Streaming-eligible count: **0**.
  3. Both candidate streaming engines (xlsxwriter constant_memory, openpyxl write_only) are therefore architecturally blocked.
- **S1.1 decision:** Ship the Phase 1 catalog doc only. Defer Excel write-path optimization to a **Sprint 2 profile-first work item** ("S2.0 — Profile workbook generation"), which will use `cProfile` + memory-profiler to identify the actual bottlenecks (suspected: column-width sizing loops, per-cell style instantiation, `clear_worksheet` calls). The real win likely comes from in-place algorithm changes inside the existing openpyxl path, not an engine swap.
- **S1.1 ships:** ✅ Phase 1 investigation report committed. Phases 2-4 cancelled.

#### S1.2 — GitHub Models alternate narrative provider

- **Goal:** Make `--narrative` work without an Anthropic key for anyone who already has a GitHub PAT.
- **Scope:** Refactor the narrative module to accept a provider strategy. Add `--narrative-provider {anthropic,github-models}` (default: `anthropic` if `ANTHROPIC_API_KEY` is set, else `github-models`). Add `--narrative-model` with sensible defaults per provider (`claude-haiku-*` for Anthropic, `gpt-4o-mini` for Models).
- **Endpoint:** `https://models.github.ai/inference`, OpenAI-compatible, auth via existing PAT with `models: read` scope.
- **Files likely affected:** Narrative module(s) under `src/`, `src/cli.py` (flags + defaults), config docs in `docs/`.
- **Tests required:** Unit tests on the provider-selection logic (no real API calls); mocked transport tests for both providers' happy path and failure cases (401, 429, missing scope).
- **Effort:** Small (≤ 1 day).
- **Exit criteria:** `audit <user> --narrative --narrative-provider github-models` produces a non-empty narrative in CI with a fake transport; `--narrative-provider anthropic` continues to behave exactly as before; docs updated.

#### S1.3 — Dependabot + CodeQL + Secret-scanning into `risk_overlay`

- **Goal:** Replace partial OSV.dev-only coverage with first-party GHAS data where available, keeping OSV as a fallback for repos without GHAS access.
- **Scope:** New `SecurityAlertsAnalyzer` that issues three GET calls per repo:
  - `/repos/{owner}/{repo}/dependabot/alerts`
  - `/repos/{owner}/{repo}/code-scanning/alerts`
  - `/repos/{owner}/{repo}/secret-scanning/alerts`
  - Aggregate counts by severity (`critical`/`high`/`medium`/`low`) and state (`open`/`dismissed`/`fixed`).
- **JSON shape:** Add a `github_security` sub-key to `risk_overlay` next to the existing `osv_vulns` field. Do not remove `osv_vulns` — keep both for reconciliation.
- **Error handling:** 403 (no access), 404 (feature disabled), 410 (deprecated) all degrade gracefully to "data unavailable" with a single warning log. Do not retry on these; respect 429 with backoff.
- **Files likely affected:** New `src/analyzers/security_alerts.py`, `src/risk_overlay.py` (or wherever risk_overlay JSON is composed), Excel security-summary sheet wiring, control-center surface.
- **Tests required:** Per-endpoint mock responses (happy path, empty, 403, 404, 429), aggregation correctness on mixed-severity inputs, downstream Excel rendering with new field present and absent.
- **Effort:** Small (2 days).
- **Exit criteria:** Risk-overlay JSON contains `github_security` with full severity/state breakdown on test fixtures; control-center shows GHAS counts; OSV path unchanged.

#### S1.4 — README staleness + release-shipped signal

- **Goal:** Add two cheap, high-signal dimensions that close common portfolio failure modes ("docs lag the code" and "has commits but never shipped").
- **Scope:**
  - **README staleness:** During clone-aware analysis, compute `readme_last_touched_days` and `code_last_touched_days` from `git log -1` on the README path and on any tracked code file. Surface `readme_staleness_ratio = readme_days / max(code_days, 1)` and a boolean `readme_stale` flag (threshold: ratio < 0.2 AND `code_days < 90`).
  - **Release-shipped signal:** Extend `ActivityAnalyzer` to call `/repos/{owner}/{repo}/releases?per_page=10` once per repo. Compute `has_any_release`, `release_count`, `latest_release_age_days`, `latest_prerelease`. Counts toward the `interest` and `completeness` dimensions in addition to standing alone.
- **Files likely affected:** `src/analyzers/readme.py`, `src/analyzers/activity.py`, `src/models.py` (new dataclass fields), Excel + control-center + portfolio-truth wiring.
- **Tests required:** Staleness math on synthetic fixtures (fresh README, ancient README, repo with no README); release endpoint mocked happy/empty/404; downstream Excel column presence.
- **Effort:** Small (1-2 days).
- **Exit criteria:** New fields land in `audit-report-*.json` and the workbook; portfolio-truth + control-center pick them up; tests cover the boundary cases.

#### S1.5 — mutmut pre-release gate on `auto_apply` + `scorer`

- **Goal:** Validate that the test suite actually catches logic regressions in the two highest-stakes modules (auto-apply touches real GitHub; the scorer drives every downstream lens).
- **Scope:**
  - Add `mutmut>=2.5` to dev extras.
  - Configure `[tool.mutmut]` with `paths_to_mutate = ["src/auto_apply.py", "src/scorer.py"]` and a `runner` of `python -m pytest -q -p no:cacheprovider -x` against the matching test files.
  - Run once locally; for every surviving mutant, write a focused test that kills it. Target ≥ 85% kill rate.
  - Document the workflow in `docs/release-gates.md` as a pre-release check (not on every push — too slow).
- **Files likely affected:** `pyproject.toml`, possibly new tests in `tests/test_auto_apply.py` and `tests/test_scorer.py`, new doc.
- **Effort:** Small (1 day for setup + iteration on surviving mutants).
- **Exit criteria:** First mutmut run completed and surviving mutants either killed by new tests or explicitly documented as equivalent mutants in `docs/release-gates.md`; kill rate ≥ 85% on both files.

#### Sprint 1 success bar

A weekly full-portfolio run finishes ≥ 30% faster, every report contains GHAS counts + release-shipped + README-staleness data, and `auto_apply`'s tests are validated to actually exercise the logic.

---

### Sprint 2 — Fetch parallelism + cache + platform reads

**Goal:** Cut the wall-clock of a full-portfolio run in half again, and start eliminating the shallow-clone for analyzers that can read from GitHub directly.

#### S2.0 — Profile workbook generation (pulled from S1.1 stop condition)

- **Scope:** Run `cProfile` + `memory_profiler` against `audit <user> --html` on a 100-repo fixture. Identify the top 5 CPU hotspots and top 3 memory accumulators in the Excel write path. Likely suspects: column-width auto-sizing loops, per-cell style instantiation, `clear_worksheet` overhead, and unnecessary `NamedStyle` recreation across sheets. Produce a ranked findings report and an opportunistic-fix list.
- **Effort:** Small (1-2 days for profiling + report; implementation of fixes is a separate sized item depending on findings).
- **Exit criteria:** Profiling report committed, top-3 quick wins implemented if they're contained to single functions; larger structural changes added to the Sprint 2 backlog.

#### S2.1 — Async fetch layer (`--fetch-workers N`, httpx)

- **Scope:** New `src/github_client_async.py` using `httpx.AsyncClient`. Bound concurrency with `asyncio.Semaphore(N)` (default N=10) and per-request exponential backoff on 429/secondary-rate-limit responses. The synchronous `GithubClient` interface stays; `async_fetch_all(repos)` is the new bulk path.
- **Tests:** Concurrency-safe stub server, rate-limit simulation, ordering invariance.
- **Effort:** Medium (3-4 days). **Exit criteria:** Full-portfolio fetch phase wall-clock drops ≥ 5x on a 100-repo run with `--fetch-workers 10`.

#### S2.2 — Per-(repo, sha, analyzer) cache in warehouse DB

- **Scope:** New `analyzer_cache` table: `(repo_name, commit_sha, analyzer_name, inputs_hash, result_json, computed_at)`. Each analyzer declares an `inputs_hash` over its inputs (e.g., the dependency analyzer hashes the lockfile bytes). Lookup before running; insert after.
- **Tests:** Cache hit and miss paths, inputs-hash sensitivity, eviction policy on warehouse DB size.
- **Effort:** Medium (2-3 days). **Exit criteria:** A second consecutive full-portfolio run on the same SHAs runs analyzers in ≤ 30% of the first run's analyzer CPU time.

#### S2.3 — SBOM-based dependency fetching + OSSF Scorecard

- **Scope:** Combine two platform reads that complement the existing dependency + security data:
  - `--sbom-source github` switches the dependency analyzer to `/repos/{owner}/{repo}/dependency-graph/sbom/generate-report` → `/fetch-report/{uuid}` (async polling). Parses SPDX 2.3 packages → existing `Dependency` dataclass. Eliminates the shallow-clone step for the dep pass.
  - OSSF Scorecard data fetched from `api.securityscorecards.dev/projects/github.com/{owner}/{repo}`. Added as a sub-key in the audit JSON.
- **Tests:** SPDX parsing fidelity, polling-loop terminations, Scorecard 404 handling (private repos), end-to-end behavior with both data sources merged.
- **Effort:** Medium (3-4 days). **Exit criteria:** Repos audited without local clones still produce a complete dependency view; Scorecard sub-scores visible in workbook security sheet.

#### S2.4 — Workbook + control-center surface wiring for new dimensions

- **Scope:** Carry the new S1+S2 fields (GHAS counts, release signals, README staleness, Scorecard sub-scores) into the Excel `Security Summary`, `Repo Detail`, and control-center triage. Add filters/sorts where appropriate.
- **Effort:** Small-to-medium (2 days).
- **Exit criteria:** No new field is "JSON only" — everything from S1 and S2 has a surfaced view.

#### S2.5 — Sprint 2 quality gate

- **Scope:** Catch any regression introduced by the async fetch layer or cache. Add a `--reconcile-cache` flag that re-runs all analyzers ignoring the cache and diffs against cached results; CI runs this monthly on a fixed fixture.
- **Effort:** Small (1 day).

---

### Sprint 3 — The AI loop

**Goal:** Promote AI from a single narrative paragraph to a portfolio analyst, anchored by one shared semantic index and a preference-memory pre-filter so suggestions stay relevant.

#### S3.1 — Portfolio semantic index

- **Scope:** Embed each repo's `{name}\n{description}\n{README[:2000]}\n{top_files_list}` using `voyage-code-3` (512-dim int8) via the Voyage API, store in a new `repo_embeddings` table with `sqlite-vec`. Reindex only when `pushed_at` changes since last index.
- **Surface:** `--reindex` flag rebuilds; `--semantic-search "query"` and `--ask "question"` (top-K cosine retrieval, prints ranked results with score and a one-line justification from the stored doc snippet).
- **Tests:** Indexing pipeline, vector storage round-trip, query relevance against a labeled mini-set of ≤ 20 known repo/query pairs.
- **Effort:** Medium (3-4 days). **Exit criteria:** Index covers all audited repos, queries return correct top-3 on the labeled set, full reindex of 150 repos finishes in < 60 seconds with cached `pushed_at`.

#### S3.2 — Weekly Operator Briefing (`--briefing`)

- **Scope:** Replace the current paragraph-style `--narrative` output with a structured Markdown:
  - **Shipped this week** — repos with commits in last 7 days, labeled by automation status.
  - **Needs attention** — top-5 repos by completeness-vs-touch gap.
  - **Portfolio health delta** — score-movers since last run.
  - **Suggested next action** — one sentence per top-3 repos (Haiku or GitHub Models, low cost).
  - Voice-readable plain-text variant (no tables, bullet sentences for TTS).
- **Files:** Extends the narrative module. Composes most content deterministically from warehouse data; LLM only for the suggested-action sentences.
- **Tests:** Section-presence assertions, fixture-based snapshot for Markdown structure.
- **Effort:** Small-to-medium (2 days).

#### S3.3 — Operator preference memory

- **Scope:** Post-process the approval/rejection ledger. When the same `(action_type, target_context)` is rejected ≥ 3 times in a row, write a suppression hint to `output/operator_prefs.json`. Future planner + drafter + briefing reads this file before proposing actions; suppressed actions get a `suppressed: true` flag in their proposal record so they're visible but de-emphasized.
- **Reset:** `audit --reset-prefs` clears suppression hints.
- **Tests:** Trigger threshold, suppression integration into briefing output, reset behavior.
- **Effort:** Small (1-2 days).

#### S3.4 — Semantic index integrations

- **Scope:** Two cheap wins built atop S3.1:
  - **Cross-repo duplication detector** — pairs with cosine > 0.85 flagged in control-center.
  - **Briefing enrichment** — when summarizing a repo, retrieve its nearest neighbors as "related repos" context for the LLM call.
- **Effort:** Small (1-2 days combined).

#### S3.5 — Sprint 3 cost guard

- **Scope:** Track per-run LLM spend in `run-telemetry.jsonl`. Add `--max-llm-spend USD` to halt runs that would exceed budget. Default disabled.
- **Effort:** Small (1 day).

---

### Sprint 4 — UI + distribution + CLI restructure

**Goal:** Make every artifact in `output/` and the warehouse browsable from a UI, make the tool one command to install on a fresh machine, and cluster the CLI so new operators don't drown in 70+ flags.

#### S4.1 — `audit serve` (FastAPI + HTMX)

- **Scope:** `audit serve --port 8080` starts an `uvicorn`-served FastAPI app. Routes:
  - `/` — portfolio dashboard from latest `portfolio-truth-latest.json`
  - `/repos/{name}` — per-repo drill-down (history, scores, alerts)
  - `/runs` — historical run browser pulling from `portfolio-warehouse.db`
  - `/approvals` — pending approval queue with form actions
  - `/runs/new` — form that constructs a CLI invocation, streams stdout via SSE
- **HTMX** handles partial refreshes; no JS build step.
- **Tests:** Route smoke tests with a fixture warehouse, form validation, SSE happy-path.
- **Effort:** Medium (3-4 days).
- **Exit criteria:** Operator can complete a full triage cycle (browse latest run → drill into a flagged repo → approve a packet → trigger an apply run) entirely from the browser.

#### S4.2 — PyPI publish + `shiv` binary

- **Scope:** Drive `__version__` via `hatch-vcs`. Add `hatch build` + `twine upload` workflow. Build a `shiv` single-file `.pyz` and attach to GitHub Releases. Update README install snippet to `uv tool install githubrepooauditor`.
- **Effort:** Small (1 day).

#### S4.3 — CLI subcommand restructure (`audit run / triage / report`)

- **Scope:** Introduce three subparsers. Migrate flags into the appropriate subcommand. Keep the legacy flat invocation working via a compatibility shim for one major version with a deprecation warning. Update all docs and example invocations to the subcommand form.
- **Tests:** Both old and new invocation forms produce identical outputs on a fixture run; deprecation warning emitted on legacy form.
- **Effort:** Medium (2-3 days).
- **Exit criteria:** `audit triage --help` shows ≤ 15 flags; `audit run --help` shows ≤ 20; total surface area is unchanged but discoverable.

#### S4.4 — Documentation refresh

- **Scope:** Rewrite README intro to lead with `audit serve`. Update `docs/modes.md` with the new subcommand verbs. Add `docs/release-gates.md` (mutmut + workbook-signoff + manual-approval workflow in one place).
- **Effort:** Small (1 day).

#### S4.5 — Arc F closeout

- **Scope:** Capture an Arc F closeout doc summarizing what shipped vs. backlog vs. deferred. Update `docs/architecture.md` if surface area changed. Confirm the trust bar still holds after async/cache changes (re-run the full approval workflow end-to-end on a real repo opt-in).
- **Effort:** Small (1 day).

---

## Backlog (post-90-day, ordered by readiness)

These are documented and scoped — they just don't fit the 90-day window. They become candidate Sprint 5+ items.

1. **Agentic README/description authoring** (`--draft-readmes`) — LLM-authored diff packets routed through the existing approval ledger. Builds on S3.1 + S3.3.
2. **Planner agent for campaign authoring** (`--plan-campaign "goal"`) — same approval-lane integration as `--draft-readmes`.
3. **Eval-driven scoring tuning** (`--tune-scoring-profile`) — operator labels small eval set; grid search over weights proposes `operator-tuned.json`.
4. **Tiered maturity + Initiative tracker** — Cortex-style 4 tiers with deadline-bound initiatives.
5. **DORA-Lite metrics** — release cadence, lead-time proxy, change-failure proxy.
6. **Star momentum + cross-repo context-switching heatmap** — visualization-heavy additions to the HTML dashboard.
7. **Year-in-review report** (`--year-review YYYY`).
8. **Cross-repo code search** (`--cross-repo-search "PATTERN"`).
9. **Repo rulesets + signing governance score expansion**.
10. **CI health analyzer** (workflow runs + cache stats).
11. **Auto-topic suggestions via LLM**.
12. **Bus-factor + commit-message hygiene + milestone hygiene** — three small dimension adds.
13. **Plugin architecture** (entry-points for `Analyzer`/`Exporter`/`Scorer`).
14. **structlog + per-phase timings** to `run-telemetry.jsonl`.
15. **Arc E desktop shell** (Tauri 2 + React) — build after `audit serve` validates which views are daily-driver material.

---

## Explicitly deferred

| Item | Reason |
|---|---|
| Webhook daemon (`--serve-webhook`) | Persistent server + GitHub App token management is operationally heavy. Only justified at portfolio scale we don't have. |
| LLM code-quality analyzer per file | Per-file LLM cost adds up across 100+ repos; existing deterministic analyzers cover ~80% of the signal. Revisit only if a specific gap is identified. |
| Local-first Ollama classification | API cost is not the constraint today. Keep simple. |
| OpenTelemetry traces | Overkill for solo tool; append-only JSONL telemetry is sufficient. |

---

## Cross-sprint principles

1. **Flag-gate every new behavior** for the first sprint it ships. Default-off until validated on real runs.
2. **No data loss on schema changes.** New JSON keys are additive; never rename or drop. Warehouse migrations are forward-only with backfill where needed.
3. **Trust bar is not bypassed.** Every new writeback path (S3 agentic drafts, S4 web UI form-triggered applies) flows through the existing approval ledger. Auto-apply still requires the three-part trust bar.
4. **Tests over benchmarks.** Performance changes (S1.1, S2.1, S2.2) add benchmark tests so we can verify the speedup claim, but a passing test suite is the hard gate.
5. **Conventional commits per logical unit**, not per sprint item — a sprint item may produce multiple commits if its concerns are independent.
6. **Demand-elegance pass before commit on items > 200 lines of diff**, per global rule. `/code-review` invoked for API contracts, auth/auth-adjacent flows, and migrations.

---

## Open questions / decisions needed

| Q | Decision needed by | Notes |
|---|---|---|
| Should `voyage-code-3` be the embedder, or a local sentence-transformer? | Sprint 3 kickoff | Voyage is best-in-class for code, but adds an API dependency. Local `all-MiniLM-L6-v2` is free but ~15% weaker. Lean Voyage; provide a `--embedder local` fallback. |
| Should `audit serve` ship behind a `--dev-only` flag in v1, or be the new default install story? | Sprint 4 kickoff | Probably ship as opt-in for a release, then promote in README once it has battle-tested under 100+-repo loads. |
| What's the acceptable mutmut kill-rate threshold? | Sprint 1 closeout | Plan says 85%. Confirm or adjust based on initial run. |
| Do we publish to PyPI under `githubrepoauditor` or rename for clarity (`gh-portfolio-auditor`)? | Sprint 4 kickoff | Current name is established locally; check PyPI availability before reserving. |

---

## How to read this plan going forward

- **Current state lives in this file.** When a sprint item ships, flip its row in the inventory from ✅ Sprint to ✅ Shipped and link the merge commit.
- **Each sprint produces a closeout entry** at the bottom of this file once complete: what shipped, what slipped, what we learned. No separate doc.
- **The backlog is reviewed at every sprint boundary.** Items can be promoted to the next sprint or demoted to deferred. The deferred list is sacred — items only leave it via a new ADR.
- **When in doubt, prefer scope reduction over silently descoping.** Per global scope-discipline rule: if a sprint item is too big, propose a phase split in this doc; do not ship a "v1" of it without saying so.

---

## Sprint closeouts

(Populated as sprints complete.)

### Sprint 1 closeout

_In progress — closeout entry to be written when all five S1 items have shipped._
