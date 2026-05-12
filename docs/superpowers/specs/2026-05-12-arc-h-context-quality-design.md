# Arc H: Context Quality Recovery — Design Spec

**Date:** 2026-05-12  
**Status:** Approved  
**Approach:** C — Parallel streams (tooling + operational)

---

## 1. Goals

Arc G shipped the operator workflow stack (maturity tiers, LLM initiative suggestions, dismissal lifecycle, web surface). The quality of that surface depends entirely on context quality — and ~53 repos in the portfolio have weak context: wrong descriptions, stale READMEs, sparse catalog entries, and miscalibrated maturity tiers.

Arc H fixes the measurement tooling and runs the recovery, in parallel. Neither stream ships alone.

**Success definition:** ≥80% of the portfolio has `context_quality_score ≥ 0.7`, and initiative suggestions are demonstrably better on recovered repos.

---

## 2. Structure

Two parallel streams converge at a merge gate:

```
Stream A (Tooling)                Stream B (Operational)
──────────────────                ──────────────────────
H.1: description_analyzer         H.3: Triage run (B1)
     README staleness                   Recovery workflow (B2)
H.2: Catalog validator            H.4: Validate outputs (B3)
     Tier recalibration                 Fix Stream A gaps
          └──────────── Merge gate ────────────┘
                    Metrics pass → ship
```

---

## 3. Stream A — Tooling

### A1: Description quality detection (`description_analyzer.py`)

Cross-reference the stored GitHub description against file-structure signals. A repo with `*.xcodeproj` but a description that says "Python CLI" is misclassified.

**Output field:** `description_confidence: float` (0.0–1.0) added to the per-repo audit dict.

**Implementation:**
- New `src/analyzers/description_analyzer.py`
- Reads `repo_files` (already collected by structure analyzer) and `description` string
- Emits confidence score based on language/framework signal agreement
- Warns below configurable threshold (default 0.5)

**Tests:** 3 fixture cases — correct classification, misclassified (iOS vs Python), missing description.

### A2: README staleness

Current check is presence/absence. New check: days since last commit touching the README file vs. days since last substantive code commit. A README untouched for ≥180 days while code has recent commits is "stale."

**Output field:** `readme_staleness_days: int | None` added to repo audit dict.

**Implementation:**
- Wire into existing `src/analyzers/readme.py`
- Use GitHub Contents API `commits` endpoint for per-file commit history (already authenticated)
- Threshold configurable in settings

**Tests:** Boundary tests at 179/180/181 days. Null case (no commits on README).

### A3: Catalog entry quality validator

`config/portfolio-catalog.yaml` entries are sparse. Validate each entry against required fields and score completeness.

**Required fields (4 minimum):** `name`, `description`, `primary_language`, `status`  
**Optional scored fields:** `tags`, `tech_stack`, `demo_url`, `notes`

**Output field:** `catalog_completeness: float` (0.0–1.0) per repo.

**Implementation:**
- New `src/catalog_validator.py`
- Runs at audit time; repos below 0.6 threshold flagged as `catalog_incomplete` in output
- No LLM calls — structural validation only

**Tests:** Each missing-field combination. Repos not in catalog at all score 0.0.

### A4: Maturity tier recalibration

If tier thresholds cause bunching (e.g., >60% of repos land Bronze), recalibrate using percentile-based cuts. Emit a report showing before/after distribution.

**Implementation:**
- New `--tier-recalibration-report` CLI flag
- Reads current audit scores across portfolio, computes percentile boundaries
- Proposes new thresholds; operator approves before they take effect
- Thresholds stored in `config/settings.yaml` (additive key, not hardcoded)

**Output:** `output/tier-recalibration-YYYY-MM-DD.json` + Markdown summary

**Tests:** Recalibration logic with synthetic distributions (uniform, skewed, bimodal).

---

## 4. Stream B — Operational Recovery

### B1: Triage run

Read-only diagnostic pass against all ~53 flagged repos.

**Output:** `output/context-triage-YYYY-MM-DD.json` with structure:
```json
{
  "repo": "string",
  "failure_modes": ["description", "readme", "catalog", "tier"],
  "severity": "critical | moderate | low",
  "context_quality_score": 0.0
}
```

Also emits a Markdown triage table for operator review.

### B2: Batch recovery

For each failure mode, run the appropriate recovery path:

| Failure mode | Recovery method |
|---|---|
| Description misclassified | `portfolio_context_recovery.py --mode description` (LLM-assisted rewrite) |
| README stale | Generate structured README stub from file inventory + description |
| Catalog incomplete | Fill missing fields from audit data (no LLM) |
| Tier mismatch | Recalibrate via A4 output; no per-repo manual work |

Recovery uses existing `src/portfolio_context_recovery.py` infrastructure (Phase 104). LLM writes go through the existing dry-run gate (`--dry-run` skips writes, validates triage output).

### B3: Validate outputs

- Capture before/after `context_quality_score` for all recovered repos
- Spot-check 5 LLM-generated descriptions manually (operator reviews)
- Re-run initiative suggestions on a 10-repo sample; assert suggestions are non-generic

---

## 5. Data model

No new schema files. New fields added **additively** to existing repo audit dict:

```python
"description_confidence": float,    # 0.0–1.0; new from A1
"readme_staleness_days": int | None, # new from A2
"catalog_completeness": float,       # 0.0–1.0; new from A3
"context_quality_score": float,      # composite; weighted average of above + existing dims
```

New config block in `config/settings.yaml`:

```yaml
context_quality:
  readme_staleness_threshold_days: 180
  catalog_completeness_min_fields: 4
  description_confidence_warn_below: 0.5
  tier_recalibration_percentile_cuts: [25, 50, 75]  # Bronze/Silver/Gold/Platinum
```

`context_quality_score` composite weight (initial):
- description_confidence: 30%
- readme_staleness (inverted, normalized): 25%
- catalog_completeness: 25%
- existing completeness dimension: 20%

Weights are config-tunable, not hardcoded.

---

## 6. Testing

| Component | Coverage target | Approach |
|---|---|---|
| `description_analyzer.py` | ≥90% branch | Unit, 3 fixture cases |
| README staleness (readme.py patch) | ≥90% branch | Unit, boundary tests |
| `catalog_validator.py` | ≥90% branch | Unit, all field combinations |
| Tier recalibration | ≥90% branch | Unit, synthetic distributions |
| `context_quality_score` composite | ≥85% branch | Unit + integration |
| B1 triage output | Integration | Real fixture repos, dry-run |
| B2 recovery pipeline | Integration | Dry-run mode, no LLM writes |

No mocking of LLM calls in integration tests. Use `--dry-run` to validate triage without committing writes.

---

## 7. Merge gate

Both streams must pass before merging to main:

| Metric | Target |
|---|---|
| Repos with `context_quality_score ≥ 0.7` | ≥80% of portfolio |
| `description_confidence < 0.5` repos remaining | ≤5 |
| `catalog_completeness < 0.6` repos remaining | ≤10 |
| README stale (>180 days) repos remaining | ≤15 |
| New test coverage (A1–A4) | ≥90% branch |
| Initiative suggestions spot-check | ≥3/5 rated "good" on manual review |

If Stream B surfaces a failure mode not covered by Stream A tooling, fix it before merge — no deferral to Arc I.

---

## 8. Sprint breakdown

| Sprint | Stream | Deliverables |
|---|---|---|
| H.1 | A | `description_analyzer.py` + tests; README staleness wired into `readme.py` |
| H.2 | A | `catalog_validator.py` + tests; `--tier-recalibration-report` + tests; new config block |
| H.3 | B | Triage run (B1); recovery workflow wired end-to-end (B2) |
| H.4 | B + A | Validate outputs (B3); fix any Stream A gaps surfaced by B; merge gate check |

**Estimated duration:** 4 sprints (~2 weeks)  
**New dependencies:** None  
**Breaking changes:** None — all new fields additive

---

## 9. Out of scope

- Automated writeback of recovered descriptions to GitHub (post-Arc H, requires separate approval flow)
- Full agentic README generation (stub only in this arc)
- Bulk catalog entry authoring via LLM (manual fill from audit data only)
- Sprint 14 pinned items (bulk dismiss/undo, CLI flags for event log limits, auto-expire heuristics)
