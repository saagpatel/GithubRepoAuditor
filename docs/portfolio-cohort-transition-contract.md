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
producer independently recomputes the candidate cohort
        ↓
R1  receipt   == required ∪ outgoing
R2  required  ∩ outgoing == ∅
R3  candidate == required                      (exact set equality)
R4  outgoing  ∩ candidate == ∅
R5  final     ⊆ receipt
R6  every departure positively explained
        ↓
transactional publication
```

R3 is the same fail-closed control the pipeline always had. It is **re-pointed**,
not relaxed: it now compares against a derived, receipt-declared set instead of a
hand-maintained integer. That is strictly stronger on membership — a same-size
swap passed the old count tripwire silently and now fails R3 with both sides
named.

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

A repository may leave the published default-attention cohort only with positive
evidence, through one of three branches:

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
`required = collected`, `outgoing = ∅`, which reproduces the pre-transition
semantics verbatim, size tripwire included. `--portfolio-truth-require-cohort-transition`
turns "a stale collector silently reverted us to a deadlock" into a named
refusal. `--portfolio-truth-security-cohort-count` is retained as a deprecated
alias for one release so a stale deployed wrapper cannot hard-error on an unknown
argument.

`cohort.expected_count` keeps its legacy meaning in every mode — the size of the
*collected* set — so the published truth's
`inputs.github_security.cohort_repository_count` binding is unchanged. No
PortfolioTruth `SCHEMA_VERSION` bump is required.
