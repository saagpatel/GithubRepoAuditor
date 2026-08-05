# Portfolio decision contract

`portfolio_decision_digest_v2` is the producer-owned admission and readback
contract for the existing portfolio decision surfaces. It does not add a queue
or approval system. GithubRepoAuditor classifies from PortfolioTruth; Personal
Ops records the operator outcome in its existing coordination outcome log; PCC
renders the same question and clocks read-only.

An actionable decision always carries a stable `decision_key`, an evidence-
generation `decision_fingerprint`, the exact question and accountable owner,
the allowed `accept` / `defer` / `reject` outcomes, an operator approval
boundary, an immutable evidence reference, `evaluated_at`,
`evidence_observed_at`, `valid_until`, source generations, and a readback
contract. The current security policy expires 36 hours after the oldest
admitted Dependabot, CodeQL, or secret-scanning observation, reflecting the
verified daily producer cadence plus one bounded grace window. Regenerating
PortfolioTruth never moves that clock.

Security decisions carry the shared `SecurityAdmissionV1` identity and the
provider-specific blocking counts. A CodeQL high/critical finding or an open
secret-scanning finding enters the same repository-scoped decision contract as
a Dependabot high/critical finding. Incomplete or contradictory admission is
retained under `withheld_decisions` with the canonical `SECURITY_*` reason code.

Incomplete owner decisions are emitted under `withheld_decisions` with stable
reason codes. They are not actionable and consumers must not invent a question
or options. A prior digest may be supplied with `--previous-digest`; the next
generation then records the superseding generation and fingerprint. A missing
decision closes only when a newer complete GitHub security receipt establishes
authoritative absence across all three providers. Bridge `SHIPPED` is supporting
evidence only and is explicitly barred from satisfying the readback contract.

The machine-readable shape is
`config/portfolio-decision-digest-v2.schema.json`. Generate JSON and Markdown
from the same PortfolioTruth generation:

```bash
python -m src.portfolio_decision_queue \
  --truth output/portfolio-truth-latest.json \
  --previous-digest output/portfolio-decision-digest-latest.json \
  --format json
```
