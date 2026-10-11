# PortfolioTruth cohort-transition contract

Protocol: `portfolio-default-attention-transition-v1`.

## The problem it removes

The security collector derived its cohort from the *published* PortfolioTruth;
the producer derived its candidate cohort from *current source*; reconcile then
required the two to be identical. The published truth can only advance through
that check, so any revision that changed default-attention membership was
unsatisfiable in both directions. No value of any cohort-count parameter
resolves it — after the size check the comparison is a set comparison.

## The protocol

```
current pinned source
        ↓ derive_candidate_cohort()            (the producer's own machinery)
prospective cohort
        +  prior published cohort
        ↓
collection = prospective ∪ prior
        ↓ bounded GitHub security collection
receipt:  required = prospective
          outgoing = prior − prospective
          collection = required ∪ outgoing
        ↓
producer independently recomputes the candidate cohort as of receipt produced_at
        ↓
R1  receipt   == required ∪ outgoing
R2  required  ∩ outgoing == ∅
R3  candidate == required                      (exact set equality)
R4  outgoing  ∩ candidate == ∅
R5  final     ⊆ receipt ∪ explicitly pending clock-only arrivals
R6  every departure positively explained
        ↓
transactional publication
```

R3 is the same fail-closed control the pipeline always had. It is **re-pointed**,
not relaxed: it now compares against a derived, receipt-declared set instead of a
hand-maintained integer. That is strictly stronger on membership — a same-size
swap passed the old count tripwire silently and now fails R3 with both sides
named.

## Receipt observation clock and pending coverage

R3 evaluates time-relative activity staleness at the receipt's timezone-aware
`produced_at` observation time. It uses the inputs observed by the current run:
activity timestamp, classification, and prior security evidence. Only the clock
changes; inputs are not restored from history. A moved HEAD, reclassification,
or real coverage gap that changes membership at that observation time still
fails the exact set comparison. Missing, invalid, or timezone-less receipt time
fails closed. Receipt freshness and publication guards still use the run/live
clock.

The same observed inputs are also evaluated at the run clock. Repositories that
enter attention only because of elapsed time are listed as **pending security
coverage**, remain in current attention, and are not counted as collected or
admitted security evidence. Covered repositories that leave attention only
because of elapsed time are recorded without failing. R1, R2, and R4 remain
strict; R4 checks the current candidate as before, so declared outgoing members
cannot become pending. Declared-outgoing departure evidence is unchanged. R6
accepts a clock-only departure only when both the pre-security and post-security
views show that departure from changing the clock alone.

`portfolio-cohort-transition-latest.json` adds these fields under `transition`:

- `receipt_observed_at`
- `pending_security_coverage_count` and `pending_security_coverage_repositories`
- `clock_departed_count` and `clock_departed_repositories`

For runs with clock differences, the same lists and counts appear under
`portfolio-truth-latest.json` → `source_summary.security_coverage_clock`, with
`receipt_observed_at` and `evaluated_at`. The portfolio Markdown report names
each pending repository and covered clock departure. These are coverage
annotations; the existing attention-state vocabulary remains unchanged.

On R3 publication failure, a unique
`portfolio-cohort-r3-failure-<run-stamp>-<unique-id>.json` is written in the
requested output directory before the error is returned. The error points to
it. It contains receipt identity/time, receipt and run evaluation clocks,
required/collected and both derived cohorts, and differing repositories'
activity timestamp/source, classification, local HEAD, and attention states.
It contains metadata only and is outside the publication transaction, so the
prior truth and reports remain untouched. In-memory snapshot builds carry the
same diagnostics on `CohortR3Error` without writing files.

Operator-scripts integration: advance `release-pins.json`'s
`auditor_truth_ref.value` to the reviewed producer commit containing this fix,
then regenerate and activate the governed release manifest. Both wrappers read
that shared pin through release preflight; keep one pin. Extend
`portfolio-maintenance.sh`'s `read_cohort_transition()` JSON projection with the
five new transition fields listed above, so its terminal-state/history
`cohort_transition` summary retains the pending repositories and clock departures.
Any digest or summary consumer should display
`pending_security_coverage_repositories` as pending (never covered/clean) and
`clock_departed_repositories` as already covered. Read the lists from the
transition outcome or the optional truth summary; absent lists mean empty for
older outputs. Exit status remains the failure gate. No new CLI flag, changed
receipt schema, attention-state enum, or hand-maintained cohort count is needed.

## Surfaces

| Component | Role |
|---|---|
| `portfolio_cohort_plan` | Derives the prospective cohort at the pinned producer revision and emits `PortfolioCohortPlanV1`. Read-only. The plan is **not** PortfolioTruth. |
| `portfolio_cohort_plan_contract` | Schema, digest rule, and validator shared by the planner and the collector. |
| `github_security_coverage` | Consumes the plan, collects the union, and writes the additive `cohort.required_repositories` / `cohort.outgoing_repositories` / `cohort.transition` receipt fields. |
| `portfolio_truth_reconcile` | Owns `derive_candidate_cohort` (the single candidate-derivation implementation) and rules R1-R6. |
| `portfolio_truth_publish` | Binds the receipt's `prior_truth_sha256` to the prior truth actually in use and publishes `portfolio-cohort-transition-latest.json` inside the same transaction. |

`derive_candidate_cohort` has exactly one implementation. The planner and the
producer both call it; `tests/test_portfolio_cohort_plan.py` asserts that, because
two equivalent algorithms would silently drift apart and reproduce the deadlock.

## Departure evidence

A source or security change may remove a repository from the published
default-attention cohort only with positive evidence, through one of three
branches (covered clock departures are handled separately above):

1. **observed resolution** — prior high+critical > 0, fresh receipt, Dependabot
   `observed`, current high = critical = 0.
2. **observed archive** — final project archived, fresh receipt, remote
   observation `archived: true`.
3. **declared source departure** — the receipt declares the repository
   `outgoing`, the receipt is fresh, Dependabot is `observed`, and high =
   critical = 0.

Branch 3 inspects Dependabot only, mirroring branch 1, because code scanning and
secret scanning are structurally `feature_unavailable` on this account's private
repositories; requiring all three would be a dead gate.

Security evidence outranks lifecycle classification. An `outgoing` member whose
fresh evidence shows an open high or critical alert is materialized as
`decision-needed`, stays in the final cohort, and is recorded as
`retained_due_security`. That is a successful transition outcome, not a failure.

**Deferred:** a departing repository that no longer exists on GitHub
(`not_found` / `gone`) cannot satisfy any branch. Slice 1 fails closed with a
named reason. The follow-on is a fourth branch, *observed non-existence*, which
needs its own fixtures and has no live instance today.

## Policy bounds

Defined exactly once, in `github_security_coverage`:

- `DEFAULT_MAX_COHORT_SIZE = 24` — fail-closed size bound on the collected union.
- `DEFAULT_MAX_COHORT_DELTA = 3` — fail-closed churn bound on
  `|prospective △ prior_published|`.

Every other surface propagates these rather than restating the number. The
four-literal synchronization problem that produced the deadlock is the reason.
Both are overridable per run (`--max-cohort-size`, `--max-cohort-delta`).

## Backward compatibility

A receipt without the transition block is legacy-shaped: reconcile falls back to
`required = collected`, `outgoing = ∅`, retaining the pre-transition partition
and size tripwire. Receipt-time recency evaluation applies in this mode too.
`--portfolio-truth-require-cohort-transition`
turns "a stale collector silently reverted us to a deadlock" into a named
refusal. `--portfolio-truth-security-cohort-count` is retained as a deprecated
alias for one release so a stale deployed wrapper cannot hard-error on an unknown
argument.

`cohort.expected_count` keeps its legacy meaning in every mode — the size of the
*collected* set — so the published truth's
`inputs.github_security.cohort_repository_count` binding is unchanged. No
PortfolioTruth `SCHEMA_VERSION` bump is required.
