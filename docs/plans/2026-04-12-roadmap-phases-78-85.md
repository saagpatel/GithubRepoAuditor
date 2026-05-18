# GitHub Repo Auditor Roadmap: Phases 78-85

**Date:** 2026-04-12  
**Branch Baseline:** `main` at `949a17d`  
**Goal:** Map the next several phases of GitHub Repo Auditor based on a direct codebase audit plus external research on software catalogs, scorecards, project health, engineering review loops, and developer-portal workflows.

---

## Executive Summary

GitHub Repo Auditor has moved beyond being just a repo audit tool.

The current product shape is:

- a portfolio audit engine
- a workbook-first weekly review system
- a read-only operator queue via `--control-center`
- a shared report layer across JSON, Markdown, HTML, workbook, and review-pack surfaces
- a deep follow-through model that tracks whether recommendations were attempted, escalated, recovered, rebuilt, re-acquired, softened, or retired

The next roadmap should **not** keep adding lifecycle states forever.

The healthiest next sequence is:

1. finish the current follow-through / revalidation arc
2. simplify the operator story so the product stays understandable
3. add stronger portfolio structure through ownership and scorecards
4. improve action execution through project-management and writeback integrations
5. improve hotspot precision and outcome feedback loops
6. harden packaging, onboarding, and product coherence

---

## Current State Audit

### What the project already does well

- Audits GitHub portfolios across 12 analyzers.
- Scores repos on completeness and interest.
- Generates JSON, Markdown, HTML, workbook, scheduled handoff, and review-pack outputs from shared facts.
- Stores history in SQLite via the warehouse.
- Supports preflight and doctor flows.
- Supports targeted, incremental, and watch-mode workflows with a baseline contract.
- Provides a read-only operator queue and review workflow through `--control-center`.
- Supports workbook release safety with `make workbook-gate` and manual signoff recording.
- Already has issue creation, campaign/writeback, governance, and scheduled-handoff building blocks.

### What the project has become

The product is now best described as a **GitHub portfolio operating system**.

The strongest current differentiator is not raw repo scoring. It is the operator loop:

- what changed
- what matters now
- what to do next
- whether earlier follow-through actually happened
- whether improvement is holding, softening, or regressing

### Current repo signals

From the repo audit performed on 2026-04-12:

- Top-level source files under `src/`: `56`
- Files under `tests/`: `160`
- Explicit `test_` functions: `142`
- CLI surface: broad, with doctor, control-center, review-pack, watch, scorecard, issue creation, manifest generation, metadata apply, README apply, governance, and writeback options
- Main operator brain: `src/operator_control_center.py`
- Shared wording / surface parity layer: `src/report_enrichment.py`
- Main human surfaces:
  - `src/excel_export.py`
  - `src/web_export.py`
  - `src/reporter.py`
  - `src/review_pack.py`

### Current product risks

The main risks are no longer “missing features.” They are:

- **surface complexity**: the operator story is getting richer faster than it is getting simpler
- **architecture drift**: `docs/architecture.md` still describes Phase 30-33 era logic while shipped behavior is now much further along
- **action gap**: the product is strong at diagnosis and review, but still less opinionated at turning recommendations into managed work
- **catalog gap**: the project has rich audit state but a weaker model of intended repo ownership, lifecycle, criticality, and purpose

---

## External Research Signals

This roadmap was informed by the following external patterns:

### 1. Software catalogs and ownership systems

Backstage’s software catalog emphasizes ownership and metadata as the source of truth for software entities, making software discoverable and maintainable at scale.

Relevant insight for this project:

- GitHub Repo Auditor should add a stronger portfolio catalog / ownership model instead of relying only on inferred repo metadata.

Source:
- [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/)

### 2. Scorecards and maturity programs

Port’s scorecards model uses rules plus maturity levels to evaluate catalog entities against standards and requirements.

Relevant insight for this project:

- GitHub Repo Auditor should evolve beyond one scoring system into configurable scorecards and maturity views by collection, repo type, or policy program.

Source:
- [Port scorecards concepts and structure](https://docs.port.io/scorecards/concepts-and-structure/)

### 3. Built-in platform health signals

GitHub itself already treats community profile / community standards as a project-health signal.

Relevant insight for this project:

- Community health and repo maintenance posture are worth keeping as first-class health signals, and can be tied more directly into action systems and scorecards.

Source:
- [GitHub community profile docs](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/accessing-a-projects-community-profile)

### 4. Supply chain and security posture standards

OpenSSF Scorecard provides automated security posture checks across build, dependency, testing, and maintenance practices.

Relevant insight for this project:

- The project already has scorecard/security coverage hooks. The next step is to make those more visible and actionable inside the operator loop and scorecard system.

Source:
- [OpenSSF Scorecard](https://scorecard.dev/)

### 5. Hotspot-driven prioritization

CodeScene emphasizes hotspots, technical debt prioritization, and behavioral code analysis over time.

Relevant insight for this project:

- Repo-level hotspots are already present, but file/module-level hotspot intelligence is the natural next step if the product wants to become more actionable for actual implementation work.

Source:
- [Behavioral Code Analysis in Practice (CodeScene)](https://codescene.com/hubfs/web_docs/Behavioral-code-analysis-in-practice.pdf)

### 6. Outcome metrics and feedback loops

DORA’s work reinforces the value of feedback loops and outcome metrics rather than static health snapshots.

Relevant insight for this project:

- GitHub Repo Auditor should eventually measure whether the operator loop itself is improving the portfolio, not just whether repos look healthy at one point in time.

Source:
- [DORA 2024 Accelerate State of DevOps Report](https://dora.dev/research/2024/dora-report/2024-dora-accelerate-state-of-devops-report.pdf)

---

## Product Direction

The product should continue evolving in this order:

1. **Finish the confidence / revalidation arc**
2. **Compress and simplify the operator story**
3. **Add stronger portfolio structure**
4. **Tighten action execution**
5. **Improve hotspot precision**
6. **Measure outcome quality**
7. **Polish onboarding and packaging**

This sequence matters.

If the project keeps adding status layers without simplification, it becomes harder to use.  
If it jumps to integrations before ownership and scorecards, the action loop will remain under-structured.  
If it never adds outcomes, it will stay smart but not self-improving.

---

## Phase 78: Reacquisition Revalidation Recovery + Confidence Re-Earning Controls

### Purpose

Finish the current follow-through arc by teaching the operator loop how restored confidence comes back after softening or retirement.

### Why this phase is next

Phases 74-77 built a detailed model for:

- recovery freshness
- reset
- rebuild strength
- reacquisition
- reacquisition durability
- confidence consolidation
- softening decay
- confidence retirement

The obvious missing piece is what happens **after** revalidation starts.

### Outcome

The system should be able to distinguish:

- under revalidation
- rebuilding restored confidence
- confidence being re-earned
- just re-earned vs holding re-earned confidence

### Main files

- `src/operator_control_center.py`
- `src/report_enrichment.py`
- `src/excel_export.py`
- `src/web_export.py`
- `src/reporter.py`
- `src/review_pack.py`

### Constraint

Keep this descriptive only. Do not change queue ordering, scoring, or trust-policy authority yet.

---

## Phase 79: Operator Model Compression + Surface Simplification

### Purpose

Make the current operator system easier to read without losing the rich internal state model.

### Why this phase should come immediately after 78

The current review-pack and drilldown surfaces are already dense. More lifecycle detail without simplification will raise cognitive load too far.

### Outcome

- Clearer top-line categories such as:
  - act now
  - watch closely
  - improving
  - fragile
  - revalidate
- Fewer exposed raw internal statuses on primary surfaces
- Better summary layering in workbook, HTML, Markdown, and review pack
- Updated architecture documentation so docs match the shipped operator logic

### Main files

- `src/report_enrichment.py`
- `src/review_pack.py`
- `src/reporter.py`
- `src/web_export.py`
- `src/excel_export.py`
- `docs/architecture.md`
- `docs/weekly-review.md`

### Constraint

This phase should simplify the product story, not add a new scoring regime.

---

## Phase 80: Portfolio Catalog + Ownership Contracts

### Purpose

Add a first-class portfolio catalog layer so repos are not only scored, but also described in terms of intended ownership and lifecycle.

### Why this matters

The current audit knows a lot about repo condition, but not enough about repo intent.

Without stronger ownership/lifecycle metadata, the operator loop cannot distinguish as well between:

- intentionally dormant repos
- abandoned repos
- experimental repos
- maintained assets
- critical projects

### Outcome

Add additive ownership and lifecycle contracts such as:

- owner or team
- repo purpose
- lifecycle state
- criticality
- desired review cadence
- intended disposition (`maintain`, `finish`, `archive`, `experiment`)

### Main files and areas

- `src/registry_parser.py`
- `src/models.py`
- `src/reporter.py`
- `src/excel_export.py`
- `src/web_export.py`
- `src/warehouse.py`
- likely one new config/schema file for local-authoritative metadata contracts

### Constraint

Keep the source of truth local-authoritative and additive. Do not require a full external developer portal.

---

## Phase 81: Custom Scorecards + Maturity Programs

### Purpose

Turn the project from one fixed scoring model into a flexible scorecard and maturity framework.

### Why this matters

Different repo classes should not all be judged by exactly the same maturity expectations.

Examples:

- internal tools
- public OSS repos
- client projects
- infrastructure repos
- experiments

### Outcome

Introduce configurable scorecards with:

- named rule sets
- maturity levels
- collection-aware or repo-type-aware evaluation
- scorecard rollups in workbook, HTML, Markdown, and review-pack surfaces

### Main files and areas

- `src/scorer.py`
- `src/config.py`
- `config/scoring-profiles/`
- `src/report_enrichment.py`
- `src/excel_export.py`
- `src/web_export.py`

### Constraint

The existing scoring model should remain supported. Scorecards should layer on top cleanly.

---

## Phase 82: Action System + GitHub Projects Integration

### Purpose

Bridge the gap between operator insight and execution by turning recommended work into managed tasks more cleanly.

### Why this matters

The project already has issue creation, campaign preview, writeback, and scheduled handoff foundations. The next step is to make work tracking easier to maintain.

### Outcome

- Sync top operator targets into a GitHub Projects board or project table
- Map operator fields into project fields such as:
  - lane
  - owner
  - checkpoint date
  - confidence
  - revalidation status
  - follow-through state
- Keep preview-first or read-only-first safety defaults

### Main files and areas

- `src/issue_creator.py`
- `src/ops_writeback.py`
- `src/scheduled_handoff.py`
- `src/github_client.py`
- `src/operator_control_center.py`

### Constraint

Do not collapse the local-authoritative model into GitHub Projects. GitHub Projects should be an action mirror, not the only source of truth.

---

## Phase 83: File/Module Hotspots + Refactoring Priority Intelligence

### Purpose

Make repo drilldowns more actionable by identifying where risk and maintenance pressure actually live inside a repo.

### Why this matters

Repo-level hotspots are helpful for deciding **which repo** to inspect. They are less helpful for deciding **where to start** inside that repo.

### Outcome

Add finer-grained hotspot intelligence using:

- churn
- complexity
- dependency fragility
- security signals
- historical pressure

Potential outputs:

- top files/modules to inspect first
- “why this hotspot matters”
- refactor vs test vs security remediation suggestion types

### Main files and areas

- `src/scorer.py`
- `src/report_enrichment.py`
- `src/excel_export.py`
- `src/web_export.py`
- `src/reporter.py`
- possibly new analyzer/helper modules

### Constraint

This should remain lightweight and portfolio-scalable. Avoid turning the tool into a full static-analysis platform.

---

## Phase 84: Portfolio Outcomes + Operator Effectiveness Metrics

### Purpose

Measure whether the operator loop itself is improving the portfolio.

### Why this matters

The product now has enough memory and follow-through state to judge not only repos, but also whether the review workflow is working.

### Outcome

Add portfolio-level outcome metrics such as:

- review-to-action closure rate
- time-to-quiet after escalation
- repeated regression rate
- recommendation validation rate
- false-positive or noisy-guidance rate
- high-pressure queue trend over time

### Main files and areas

- `src/operator_control_center.py`
- `src/warehouse.py`
- `src/history.py`
- `src/report_enrichment.py`
- `src/excel_export.py`
- `src/web_export.py`

### Constraint

These metrics should be descriptive first. Avoid premature gamification.

---

## Phase 85: Packaging, Onboarding, and Product Hardening

### Purpose

Make the project easier to adopt and easier to operate without losing power.

### Why this matters

By this point, product clarity will be more important than another feature layer.

### Outcome

- Better first-run onboarding
- Cleaner recommended default paths
- Tighter README + docs alignment
- Clearer beginner and advanced workflows
- Less duplication across workbook/HTML/Markdown summaries
- More explicit product modes such as:
  - first run
  - weekly review
  - deep dive
  - action sync

### Main files and areas

- `README.md`
- `docs/weekly-review.md`
- `docs/operator-troubleshooting.md`
- `src/cli.py`
- `src/reporter.py`
- `src/review_pack.py`
- `src/web_export.py`
- `src/excel_export.py`

### Constraint

This phase should reduce friction and duplication, not add another workflow branch unless it clearly replaces a confusing one.

---

## Recommended Sequencing

### Wave 1: Finish and simplify

- Phase 78
- Phase 79

### Wave 2: Add structure

- Phase 80
- Phase 81

### Wave 3: Turn insight into managed action

- Phase 82
- Phase 83

### Wave 4: Measure and harden

- Phase 84
- Phase 85

---

## Roadmap Principles

These principles should continue guiding the roadmap:

1. **Artifact-first**
   Prefer outputs that stay inspectable and useful without requiring a live hosted service.

2. **Workbook parity matters**
   The workbook remains the primary operator surface overall. New stories should mirror across workbook, HTML, Markdown, and review pack.

3. **No accidental platform sprawl**
   Prefer additive layers that build on existing local-authoritative models instead of introducing unnecessary new systems of record.

4. **Descriptive before prescriptive**
   Follow-through, trust, and outcome layers should be explanatory first. Ranking or authority changes should happen only when enough evidence exists.

5. **Simplify after rich modeling**
   Rich internals are acceptable if surface complexity is compressed for users.

---

## Recommended Immediate Next Move

If work is continuing right away, the best next implementation plan is:

- ship **Phase 78**
- then immediately schedule **Phase 79**

That pairing lets the project finish the current confidence/revalidation arc while also protecting the product from becoming too hard to understand.

---

## Handoff Notes For The Next Session

The next session should assume:

- current `main` already includes Phase 77 and the README refresh
- the roadmap in this file is the current planning baseline
- the project’s center of gravity is now the operator loop, not just analyzers
- the next implementation target is **Phase 78**
- Phase 79 should be treated as a deliberate simplification pass, not an optional cleanup

