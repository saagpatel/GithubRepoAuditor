# Arc G — Sprint 7A: Tiered maturity + Initiative tracker

**Status:** Sprint 7A / Arc G. Drafted 2026-05-12. Ships immediately after Sprint 7B in the same session per operator instruction.

**Why now:** Item 4 from the Arc F backlog. The portfolio has 100+ repos but operator has no formal way to commit to "I will get X to a higher quality bar by Y date". Sprint 7A introduces a 4-tier maturity model derived from existing analyzer output, plus a thin layer for deadline-bound initiatives.

---

## Scope

A formal 4-tier maturity model (Bronze / Silver / Gold / Platinum) computed from existing analyzer scores, plus an initiative tracker that lets the operator commit to a target tier by a deadline.

### Tier definitions

| Tier | Bar | Typical criteria |
|---|---|---|
| **Bronze (T1)** | Working code, no formal hygiene | Has README (any), at least one commit, public |
| **Silver (T2)** | Documented and tested | README ≥ 200 chars, has tests, has CI workflow, ≤ 365 days since last commit |
| **Gold (T3)** | Production-grade | All of T2 plus: shipped release, security-alerts clean (no high/critical), license present, README staleness ≤ 5x |
| **Platinum (T4)** | Mission-critical, maintained | All of T3 plus: ≤ 90 days since last commit, ≥ 2 releases in last 365 days, no abandoned dep flags |

Tier criteria are deterministic — they map to analyzer fields already in the audit pipeline. No LLM involvement.

### Initiative tracker

- Operator commits to a target tier + deadline for a repo: `audit triage --set-initiative REPO --target-tier 3 --deadline 2026-06-15`
- Initiative status (derived): `on-track` if current tier == target OR delta is closing AND deadline > 14d, `at-risk` if delta is unchanged AND deadline ≤ 14d, `overdue` if deadline passed AND not met
- Briefing (S3.2) surfaces initiatives in their own top section
- Excel adds an "Initiative Tracker" sheet
- Web UI: `/initiatives` page with progress bars (current dimension scores vs target tier's bar)

---

## Inventory

| # | Item | Status | Notes |
|---|---|---|---|
| 7A.1 | `src/maturity_tiers.py` — `TierCriteria` dataclass, `compute_tier(repo)` returning 1-4, `tier_gap(repo, target)` returning per-criterion deltas | ⏳ | Pure function; reads existing analyzer fields |
| 7A.2 | `src/initiatives.py` — `Initiative` dataclass, `output/initiatives.json` persistence (atomic tmp+rename), `derive_status(initiative, repo)` returning {on-track, at-risk, overdue, met} | ⏳ | Pattern: `src/operator_prefs.py` |
| 7A.3 | CLI: `audit triage --set-initiative REPO --target-tier N --deadline YYYY-MM-DD`, `audit triage --initiatives` (list), `audit triage --close-initiative REPO` | ⏳ | Validate target-tier > current-tier |
| 7A.4 | Excel: new "Initiative Tracker" sheet with on-track / at-risk / overdue swimlanes, per-criterion gap visualization | ⏳ | openpyxl, reuse styling helpers |
| 7A.5 | Briefing integration (S3.2): top section "Initiatives this week" with status counts + per-initiative one-liner | ⏳ | Additive to existing briefing |
| 7A.6 | Web UI: `/initiatives` route + template; per-initiative progress bar per criterion; "View tier gap" HTMX partial showing which T3 bars aren't yet met | ⏳ | Reuses S4.1 + S6.3 partial pattern |
| 7A.7 | Tests + Sprint 7A closeout | ⏳ | Final |

---

## Subagent dispatch plan

Three subagents, parallel where possible:

1. **Agent 1 — Core (7A.1 + 7A.2 + 7A.3)** — module + persistence + CLI. Foundation. Must land before others.
2. **Agent 2 — Excel + briefing (7A.4 + 7A.5)** — depends on Agent 1's CLI persistence. Pure read-side surfaces.
3. **Agent 3 — Web UI (7A.6)** — depends on Agent 1's persistence. Independent of Agent 2.

Sequential: 1 → (2 ∥ 3 in parallel) → closeout.

Estimated effort: 3-4 days. ~40-60 new tests.

---

## Schema

```python
@dataclass(frozen=True)
class TierCriteria:
    tier: int                 # 1-4
    name: str                 # "Bronze" | "Silver" | "Gold" | "Platinum"
    requirements: list[str]   # human-readable bullets ("README ≥ 200 chars")

@dataclass(frozen=True)
class TierGap:
    current_tier: int
    target_tier: int
    missing_requirements: list[str]  # what blocks the target tier today

@dataclass(frozen=True)
class Initiative:
    repo_name: str
    target_tier: int
    deadline: str          # ISO date
    set_at: str            # ISO timestamp
    set_by: str            # operator identity (default: $USER or "operator")
    closed_at: str | None  # set when --close-initiative
    closed_reason: str | None  # "met" | "abandoned" | "deadline-extended"
```

Persistence in `output/initiatives.json`:

```json
{
  "version": 1,
  "initiatives": [
    {
      "repo_name": "Wavelength",
      "target_tier": 3,
      "deadline": "2026-06-15",
      "set_at": "2026-05-12T...",
      "set_by": "operator",
      "closed_at": null,
      "closed_reason": null
    }
  ]
}
```

Atomic tmp+rename writes, same pattern as `src/operator_prefs.py` (S3.3).

---

## Exit criteria

- `audit triage --set-initiative Wavelength --target-tier 3 --deadline 2026-06-15` writes the initiative to `output/initiatives.json`
- `audit triage --initiatives` prints a status table for all open initiatives
- `audit triage --close-initiative Wavelength` marks the initiative `closed_at` + `closed_reason`
- Excel "Initiative Tracker" sheet renders with on-track / at-risk / overdue swimlanes
- `--briefing` includes the initiatives section
- Web UI `/initiatives` page shows progress bars
- 1585 → ~1640 tests (+40-60 new)
- Boot test: `audit triage --initiatives` with no `initiatives.json` exits cleanly with empty list
- Sprint 7A closeout appended

---

## Constraints

1. **MUST NOT break existing tests.**
2. **Tier criteria are deterministic** — derived from analyzer output already in `portfolio-truth-latest.json` or warehouse. No LLM calls. (Sprint 8 could add LLM-suggested initiatives, but not 7A.)
3. **`initiatives.json` schema is versioned.** v1 means missing fields default to safe values; future versions can extend additively.
4. **Tier upgrades require deliberate work — they don't auto-close.** Even if a repo hits the target tier organically (e.g. operator pushed a release), the initiative stays open until `--close-initiative` or until the deadline passes. This prevents silent "completion" claims.
5. **Subagent base-SHA discipline + cwd hygiene** as established.
6. **Briefing addition (7A.5) preserves existing briefing shape** — add a section, don't reshape.

---

## Open question (resolve at kickoff)

| Q | Default | Notes |
|---|---|---|
| When an initiative passes its deadline without meeting target tier, auto-mark `overdue` (visible flag) or auto-close with `reason=overdue`? | **Auto-mark `overdue` only; require explicit close.** | Forces the operator to decide: extend deadline, abandon, or admit the work is done. |
| Should Bronze (T1) be the implicit default for every repo, or do we require an initiative to "be in T1"? | **T1 is implicit; T1 has no initiatives.** Initiatives only target T2+. | Bronze means "exists and works enough"; you don't commit to staying Bronze. |
| Where does the operator identity (`set_by`) come from? | `$USER` env var, fallback to `"operator"`. | Same pattern as approval-ledger reviewer (Arc D). |
