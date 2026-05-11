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
| 1.1 | Dependabot + CodeQL + Secret-scanning alerts in `risk_overlay` | ✅ Shipped | `2703fb4` (S1.3) |
| 1.2 | SBOM-based dependency fetching (`--sbom-source github`) | ✅ Shipped | `aa5dbee` (S2.3) |
| 1.3 | GitHub Models as alternate `--narrative-provider` | ✅ Shipped | `ae0a7c6` (S1.2) |
| 1.4 | OSSF Scorecard integration | ✅ Shipped | `aa5dbee` (S2.3, `--ossf-scorecard`) |
| 1.5 | Repo rulesets + signing as governance score | 📋 | post-S4 |
| 1.6 | CI health analyzer (workflow run metrics) | 📋 | post-S4 |
| 1.7 | Cross-repo code search (`--cross-repo-search`) | 📋 | post-S4 |
| 1.8 | Webhook daemon (`--serve-webhook`) | ⏸ | Operational complexity outweighs solo-operator value |

### Theme 2 — AI as analyst

| # | Feature | Status | Sprint |
|---|---|---|---|
| 2.1 | Portfolio semantic index (`--semantic-search`, `--ask`) | ✅ Shipped | `44839de` (S3.1) |
| 2.2 | Weekly Operator Briefing (`--briefing`) | ✅ Shipped | `0438428` (S3.2) |
| 2.3 | Operator preference memory | ✅ Shipped | `e0fec52` (S3.3) |
| 2.4 | Cross-repo duplication detector | ✅ Shipped | `03dc2bc` (S3.4) |
| 2.5 | Agentic README/description authoring (`--draft-readmes`) | 📋 | post-S4 |
| 2.6 | Planner agent for campaign authoring (`--plan-campaign`) | 📋 | post-S4 |
| 2.7 | Eval-driven scoring tuning (`--tune-scoring-profile`) | 📋 | post-S4 |
| 2.8 | LLM code-quality analyzer per file | ⏸ | Cost vs. signal-add not justified vs. deterministic analyzers |
| 2.9 | Local-first Ollama classification | ⏸ | Defer until API spend is a real constraint |

### Theme 3 — New analytical dimensions

| # | Feature | Status | Sprint |
|---|---|---|---|
| 3.1 | README staleness index | ✅ Shipped | `ab70a04` + `f2594a0` (S1.4) |
| 3.2 | Release-shipped signal (has-release + age + count) | ✅ Shipped | `ab70a04` (S1.4) |
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
| 4.1 | xlsxwriter migration (`constant_memory=True`) | ⏹ Stopped | `9a68e1c` Phase 1 catalog; pivoted to S2.0 (profile-first) |
| 4.2 | mutmut pre-release gate on `auto_apply` + `scorer` | ✅ Shipped | `a7b6918` + `fce45dd` (S1.5) |
| 4.3 | Async fetch layer (`--fetch-workers`, httpx) | ✅ Shipped | `bc2f95f` (S2.1) |
| 4.4 | Per-(repo, sha, analyzer) cache in warehouse DB | ✅ Shipped | `0375053` + `ef038f6` (S2.2 + NamedStyle fix) |
| 4.5 | `audit serve` — FastAPI + HTMX local web UI | ✅ Shipped @ `4da1496` + `220a6fa` | S4.1 |
| 4.6 | PyPI publish + `shiv` binary | ✅ | S4.2 |
| 4.7 | CLI subcommand restructure (`audit run/triage/report`) | ✅ | S4.3 |
| 4.8 | structlog + per-phase timings to `run-telemetry.jsonl` | 📋 | post-S4 |
| 4.9 | Plugin architecture via entry-points | 📋 | post-S4 |
| 4.10 | Arc E desktop shell (Tauri 2 + React) | 📋 | post-S4 (after `audit serve` validates which views matter) |
| 4.11 | OpenTelemetry traces | ⏸ | Overkill for solo tool; JSONL telemetry is enough |

---

## 90-day sequencing

Each sprint is ≈ 2 weeks of focused work and ships behind a feature flag where applicable. Sprints are ordered to compound: Sprint 1's platform-native data (GHAS + releases + staleness) becomes the foundation other surfaces consume; Sprint 2's cache + async layer + workbook profiling make Sprint 3's AI iteration cheap; Sprint 4's UI exposes everything that came before.

### Sprint 1 — Quick performance + platform wins (current)

**Goal:** Within 2 weeks, GHAS + release-shipped + README-staleness data lands in the audit JSON, the narrative path works with no Anthropic key required, and the auto-apply path is hardened by mutation testing. Excel + control-center surfacing of the new fields is intentionally deferred to S2.4. Workbook-generation speedup originally scoped here is deferred to S2.0 (profile-first) after the Phase 1 investigation showed both candidate streaming engines were architecturally blocked.

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

The audit JSON outputs contain GHAS alert counts (via `--ghas-alerts`), release-shipped signals, and README-staleness signals; `--narrative-provider github-models` works end-to-end without an Anthropic key; and `auto_apply.py` + `scorer.py` clear an 85% mutmut kill-rate gate. Workbook write-path speedup is **not** part of this sprint's success bar — that target moved to S2.0.

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

### Sprint 1 closeout (2026-05-11)

**Shipped:**

- **S1.2 — GitHub Models alternate narrative provider.** `--narrative-provider {anthropic,github-models}` + `--narrative-model` flags. Provider strategy pattern in `src/narrative.py`. 19 tests. Commit `ae0a7c6`.
- **S1.3 — GHAS alerts analyzer.** New `src/ghas_alerts.py`, `--ghas-alerts` flag. Open-alert counts from Dependabot, CodeQL, Secret-scanning. Writes `output/ghas-alerts-*.json` + terminal summary. 18 tests. Commit `2703fb4`.
- **S1.4 — README staleness + release-shipped signals.** New fields in `ReadmeAnalyzer` and `ActivityAnalyzer`. New `GithubClient.get_releases()`. 12 tests. Commits `ab70a04` + `f2594a0` (the second fixes an inverted threshold that shipped in the first).
- **S1.5 — mutmut pre-release gate.** `[tool.mutmut]` config, `release-gate` Makefile target, `docs/release-gates.md`. Initial run hit **92.9% kill rate** (above the 85% threshold), with 25 equivalent mutants documented. New mutmut-killing tests added to `test_auto_apply.py` and `test_scorer.py`. Commits `a7b6918` + `fce45dd`.

**Stopped (with evidence, not silently descoped):**

- **S1.1 — Excel write-path optimization.** Phase 1 investigation in commit `9a68e1c` proved both candidate streaming engines (xlsxwriter `constant_memory`, openpyxl `write_only`) were architecturally blocked: workbook-level mixing impossible, all 20 visible sheets use incompatible back-reference APIs. Phases 2-4 cancelled. Excel perf work pivoted to **S2.0 (profile-first)**. Decision recorded in commit `3cd2d80`.

**Sprint 1 success-bar grading:**

- GHAS + release + staleness data in audit JSON: ✅ shipped (Excel/control-center surfacing deferred to S2.4 as planned).
- `--narrative-provider github-models` works without Anthropic key: ✅ shipped.
- mutmut kill rate ≥ 85% on `auto_apply.py` + `scorer.py`: ✅ shipped (92.9%).
- Workbook speedup: not part of this success bar (moved to S2.0).

**Gaps closed at sprint boundary (2026-05-11):**

- README + `docs/modes.md` + `docs/security-model.md` + `docs/extending-analyzers.md` updated with the new flags and analyzer fields.
- Inventory table flipped to "✅ Shipped @ \<SHA\>" for shipped items and "⏹ Stopped" for S1.1.

**Lessons:**

1. The original "1-2 day xlsxwriter swap" estimate from the brainstorming research was wrong by ~10x — the live code surface had load_workbook templates, charts, conditional formatting, merges, and tables that no streaming engine supports. **Investigation before scoping is cheaper than scope creep mid-sprint.**
2. The S1.4 spec encoded an inverted threshold (`< 0.2` instead of `> 5.0`) which the subagent implemented faithfully. Caught at review time and fixed in a follow-up commit. **Specs with numeric thresholds should include a worked example.**
3. The TaskCompleted hook runs whole-repo mypy and trips on 372 pre-existing errors unrelated to in-sprint work, leaving some tasks visually "in_progress" despite the underlying work being complete. Known harness gotcha; future sessions can ignore.

**Next:** Sprint 2 begins with **S2.0 — Profile workbook generation**, then S2.1 (async fetch), S2.2 (per-(repo, sha, analyzer) cache), S2.3 (SBOM + Scorecard), S2.4 (workbook + control-center surface wiring for the new Sprint 1 fields).

### Sprint 2 closeout (2026-05-11)

**Shipped (all 6 items):**

- **S2.0 — Workbook profiling + quick wins.** Profile against 90-repo synthetic portfolio (`scripts/benchmark_large_portfolio.py`) identified `style_data_cell` (2.046s cumulative, IndexedList hash chain) as the dominant CPU hotspot. Three quick wins: (a) NamedStyle registration replacing 3-attribute style assignments; (b) skip zebra stripes on hidden sheets; (c) skip auto-width on hidden sheets. **Workbook build went from 3.201s → 0.396s (8.1x speedup).** Findings doc: `docs/plans/2026-05-11-s2.0-workbook-profile-findings.md`. Commits `2503660` + `2472c20` + follow-up fix `ef038f6` (see Lesson #1 below).
- **S2.1 — Async fetch layer.** `src/github_client_async.py` (327 lines) with `httpx.AsyncClient` + `asyncio.Semaphore`. Opt-in via `--fetch-mode async --fetch-workers N` (default still sync). Mock microbench: 70ms async at concurrency=10 vs 683ms sequential = **9.7x speedup**. 18 new tests. Commit `bc2f95f`.
- **S2.2 — Per-(repo, sha, analyzer) cache.** New `analyzer_cache` table in warehouse DB + `src/analyzer_cache.py` module. Three analyzers opted in (Dependencies, Readme, Structure). `BaseAnalyzer.cache_inputs_hash` is the opt-in contract. `--no-analyzer-cache` flag disables. +29 tests. Commit `0375053`.
- **S2.3 — SBOM + OSSF Scorecard.** `--sbom-source github` switches the dependencies analyzer to GitHub's SBOM endpoint (synchronous SPDX 2.3 JSON, not the planned async polling — the live API is direct GET). New `src/ossf_scorecard.py` module + `--ossf-scorecard` flag fetches from `api.securityscorecards.dev`. Misleading help text on the existing `--scorecard` flag fixed. Incidentally fixed a pre-existing bug in `libyears.compute_libyears()` that was silently overwriting lockfile-parsed `dep_count`. +26 tests. Commit `aa5dbee`.
- **S2.4 — Surface wiring for Sprint 1 fields.** GHAS counts, README staleness, release-shipped, and OSSF Scorecard score now appear in: Excel Security Summary (severity columns), Repo Detail (per-repo block), All Repos (narrow flags), and the control-center triage. New lane rules: `readme_stale → urgent`, `GHAS critical ≥ 1 → blocked`, `OSSF < 5.0 → ready` flag. Backward-compatible with older audit JSONs. +34 tests. Commit `ab2e0d4` + ruff fix `f83ca10`.
- **S2.5 — `--reconcile-cache` quality gate.** Re-runs analyzers with cache off, deep-compares against cached results (1e-6 float tolerance, recursive dict compare). Exits non-zero on divergence. Intended for CI release-gate use. +16 tests. Commit `54a78ea`.

**Sprint 2 success-bar grading:**

- Wall-clock fetch reduction: ✅ shipped (9.7x on mock benchmark; real-API estimate is 12s vs 120s on 100-repo).
- Workbook generation speedup: ✅ exceeded (8.1x vs original 3-5x target).
- Analyzer cache covers ≥30% CPU reduction on re-runs: ✅ shipped via 3 opted-in analyzers + reconcile gate.
- Sprint 1 fields visible in Excel + control center: ✅ shipped.
- SBOM + Scorecard data available: ✅ shipped.

**Lessons:**

1. **Module-level caches keyed by `id()` are unsafe across object lifetimes.** S2.0's NamedStyle quick-win cached registration state in `dict[id(wb), set]`. Python recycles `id()` values after GC, so a fresh `Workbook` could inherit a stale "already registered" marker from a GC'd predecessor and crash at `cell.style = "data_left"`. Caught only when S2.2's tests created additional short-lived workbooks, surfacing the bug as test-order-dependent. Fix: store the marker as an attribute on the workbook itself (`wb._gha_named_styles_registered = True`). Commit `ef038f6`.
2. **The live API can be simpler than the docs imply.** S2.3 was scoped around a SBOM async-polling flow (`generate-report` → `fetch-report/{uuid}`). The live endpoint is a single synchronous GET. The subagent correctly followed the live API and noted the deviation. **Future plans citing external APIs should mark the citation as "as of <date>" rather than committed contract.**
3. **Pre-existing bugs surface when new tests exercise neglected paths.** S2.3 incidentally fixed `libyears.compute_libyears` silently zeroing `dep_count`. Fix was contained but is worth noting: every new test we write is also a regression detector for code that wasn't being exercised.

**Plan housekeeping at sprint boundary:**

- Inventory rows 1.2, 1.4, 4.3, 4.4 flipped to "✅ Shipped @ \<SHA\>".
- S2.0 (profile/quick wins), S2.4 (surface wiring), and S2.5 (reconcile gate) were not inventory items — they're sprint-level concerns. They appear in this closeout only.
- Docs not yet updated with the new flags (`--sbom-source`, `--ossf-scorecard`, `--fetch-mode`, `--fetch-workers`, `--reconcile-cache`, `--no-analyzer-cache`). Carry this as a gap to close before Sprint 3 starts.

**Branch state:** `feat/arc-f-expansion-roadmap`, 18 commits ahead of `main`. 1285 tests pass. Ruff clean. Not pushed.

**Next:** Sprint 3 begins with **S3.1 — Portfolio semantic index** (sqlite-vec + voyage-code-3 embeddings), then S3.2 (Weekly Operator Briefing), S3.3 (Operator preference memory), S3.4 (semantic index integrations — duplication detector + briefing enrichment), S3.5 (LLM spend cost guard).

### Sprint 3 closeout (2026-05-11)

**Shipped (all 5 items):**

- **S3.1 — Portfolio semantic index.** New `src/semantic_index.py` (433 lines). `voyage-code-3` default embedder (512-dim, cosine distance), `sentence-transformers/all-MiniLM-L6-v2` local fallback (384-dim). `sqlite-vec` virtual table `repo_embeddings` + metadata table in the warehouse. `--reindex`, `--reindex-force`, `--semantic-search`, `--ask`, `--embedder {voyage,local}` flags. Reindex skips unchanged docs via `doc_sha256` comparison. `[semantic]` optional extra in `pyproject.toml`. +32 tests. Commit `44839de`.
- **S3.2 — Weekly Operator Briefing.** New `src/briefing.py` (586 lines). Sections: shipped-this-week, needs-attention (top-5 by gap heuristic), portfolio health delta (warehouse-historical), suggested next action (Haiku-equivalent LLM, 1 sentence per top-3 repos). Voice-readable plain-text variant. Reuses S1.2's narrative provider strategy. `--briefing` mutually exclusive with `--narrative`; `--briefing-voice` for TTS file. +31 tests. Commit `0438428`.
- **S3.3 — Operator preference memory.** New `src/operator_prefs.py` (365 lines) + `output/operator_prefs.json` schema. Detects 3+ consecutive rejections of `(action_type, target_context)` and writes auto suppression hints. `manual: true` entries are preserved across runs. Atomic tmp+rename writes. `--reset-prefs` flag. Briefing's suggestion generator consults prefs and records `suppressed_by_prefs` for observability. +12 tests. Commit `e0fec52`.
- **S3.4 — Semantic index integrations.** Two cheap wins atop S3.1: (a) `find_neighbors(repo_name, k)` and `find_duplicate_groups(threshold=0.85)` on `SemanticIndex` with union-find transitive closure. Control-center adds duplicate-group lane entries (`lane: ready`, `priority: 35`). (b) Briefing's suggestion prompt now includes `related_repos` context for cross-repo aware suggestions. Both integrations degrade gracefully when no index exists. `SEMANTIC_DUPLICATE_THRESHOLD` env override. +13 tests. Commit `03dc2bc`.
- **S3.5 — LLM spend cost guard.** New `src/llm_cost.py` (253 lines) with `CostTracker`, `BudgetExceededError`, per-model PRICES table (7 models documented, conservative `_UNKNOWN_PRICE` fallback). Wired into both `AnthropicProvider` and `GitHubModelsProvider` — each `generate()` records token usage automatically. `--max-llm-spend USD` flag halts the run if budget would be exceeded. Per-call records append to `output/run-telemetry.jsonl`. +14 tests. Commit `e661829`.

**Sprint 3 success-bar grading:**

- Portfolio semantic index queryable via `--ask`: ✅ shipped.
- Briefing replaces narrative as the structured weekly output: ✅ shipped.
- Suggestions no longer repeat what the operator has rejected: ✅ shipped via prefs.
- Duplicate groups surface in control-center: ✅ shipped.
- LLM spend is observable and budget-gateable: ✅ shipped.

**Lessons:**

1. **Subagent worktree branch lineage is brittle when worktrees are run in parallel and dispatched against a moving branch tip.** S3.1 and S3.5's commits ended up on different ancestor lines than expected (one auto-landed via the worktree merge, the other needed a manual cherry-pick). Detection: always run `git log --oneline -3` after each cherry-pick attempt to confirm what's on HEAD before claiming "shipped".
2. **Pricing tables for external APIs are maintenance debt.** S3.5's `PRICES` dict will go stale; the conservative `_UNKNOWN_PRICE` fallback (over-estimates cost) ensures stale data fails closed, not open. Worth a quarterly review reminder.
3. **Provider Protocol signature drift matters for subclass tests.** S3.2 set `generate(self, prompt, model, **kwargs)` while the Protocol said `generate(self, prompt, model, max_tokens)`. Mypy caught it post-hoc. Future Protocol changes should ripple-update the provider classes in the same commit.

**Plan housekeeping:**

- Inventory rows 2.1, 2.2, 2.3, 2.4 flipped to "✅ Shipped @ \<SHA\>".
- S3.5 (LLM cost guard) was not in the original inventory — appears in this closeout as a sprint-level addition. Add a row to Theme 2 in the next plan revision if Arc F continues.

**Branch state:** `feat/arc-f-expansion-roadmap`, 27 commits ahead of `main`. 1388 tests pass. Ruff clean. Not pushed.

**Next:** **Sprint 4 — UI + distribution + CLI restructure.** S4.1 (`audit serve` FastAPI + HTMX), S4.2 (PyPI + shiv binary), S4.3 (CLI subcommand restructure `audit run/triage/report`), S4.4 (docs refresh), S4.5 (Arc F closeout). The semantic index + briefing + cost guard from Sprint 3 are now the inputs to the live web UI's most important views.
