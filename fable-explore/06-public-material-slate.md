# Public Material Slate (draft — angles, not yet drafts)

*What already exists, what's genuinely open, and what I'd build. Public-safe = mechanics,
reasoning, and the allowlisted pilot-repo signals the site already serves. Never the estate.*

## Coverage map — the two existing pieces

| Piece | Its claim | What it deliberately skips |
|---|---|---|
| *A Portfolio Is an Observability Problem* (note) | Too many repos = observability problem; audit → truth file → cockpit → page-as-last-mile; portfolio is a map of judgment | HOW verdicts are computed; the trust problem of the pipeline itself |
| *The Ghost in the Tauri Repos* (essay) | Polished repos lie; liveness is a claim requiring evidence of ongoing expenditure; zombie tier | "The mechanics matter less than the posture" — the mechanics, explicitly |

The open lane is exactly the mechanics and the epistemics: neither piece shows the machine
deciding, doubting itself, or defending its own freshness.

## The slate (ranked)

### B1 — Interactive explainer: **"The Verdict Machine"** (flagship) — ✅ BUILT, see [verdict-machine/](verdict-machine/)
Self-contained HTML/JS. Visitor gets a synthetic repo and levers for its raw signals:
- days since last commit (scrubber), GitHub-archived toggle
- the six context sections as toggles (What-This-Is … Next-Move), supporting-file count
- declared operating path + whether an explicit catalog contract exists
- criticality, security alert counts, disposition

Right side: the live cascade — activity status → context quality → path confidence →
attention lane → risk tier — each stage a node that lights up and shows its *rationale
string*, faithfully ported from the actual pure functions (they're deterministic dict-in
dict-out; a JS port can be exact, and I can golden-test the port against the Python).
Preset buttons: "the ghost" (polished + silent), "the honest workhorse", "the thin-docs
trap" (active but boilerplate → decision-needed), "the resting archive."
**Why it lands:** the site's whole thesis is receipts over claims; this lets a visitor
*operate* the receipt machine. Complements Ghost (posture) with mechanics. No estate data
needed — entirely synthetic inputs, real logic.

### B2 — Essay: **"Who Audits the Auditor?"**
The untold half of the observability note: a truth pipeline is itself software that rots.
The drift war stories are all real and public-safe as mechanisms: consumers re-deriving
risk logic (why rollups ship from the producer), the snapshot that goes stale overnight
(freshness checks), identity drift across systems (the seam linter), scheduled runs that
exit 0 having produced nothing (producer evidence, PRs #169/#170). Thesis: monitoring
that can't prove its own freshness is just confident stale data — the same lie the ghost
repos tell, one level up.

### B3 — Essay: **"Permission to Ignore"** (deferral as a feature)
130+ repos are governable only because the system's main output is what NOT to look at:
the `deferred` risk tier, the parked lane, the capped decision queue, and the standing
instruction stamped on every queue item: *do not refresh docs unless it resolves this
decision*. Anti-busywork encoded as data — pointed at the current failure mode of agents
doing documentation theater. Also carries the epistemics angle: the system never says "bad
repo," it says "I can't advise you here yet" (confidence gates guidance, not judgment).

### B4 — Written teardown + diagram: **"Anatomy of a Health Verdict"**
The public-safe version of fable-explore/01: the full cascade with pseudo-code and one
clean pipeline diagram (sources → precedence → reconcile → derived → rollups → publish →
consumers, seam linter wrapped around). Companion text for B1 — the explainer shows it,
the teardown explains why each threshold and short-circuit exists. Could live as a note.

### Considered, weaker
- "Two kinds of context quality" — real tension but inside-baseball; folds into B4.
- Fleet-dashboard screenshots tour — violates the "genuinely interactive, not screenshots"
  bar and risks estate leakage. Rejected.
- Live portfolio health widget from real data — the site already has the repos page +
  heartbeat; incremental, and freshness liability. Rejected for now.

## Sequencing I'd propose
1. B1 (flagship, most differentiated, hardest)
2. B2 (strongest new essay claim, feeds on recent PRs)
3. B4 (cheap once 01 exists; pairs with B1 at launch)
4. B3 (evergreen, can trail)

*Pending: field-research scout (04) may adjust B1 mechanics (scrubber vs presets emphasis,
progressive disclosure patterns).*
