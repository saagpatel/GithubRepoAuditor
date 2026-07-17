# Reconciliation: 60-vs-110 declared-active discrepancy (resolved 2026-07-17)

Routed from the KEEP-Tier Atlas (repository-renaissance,
`docs/KEEP-TIER-ATLAS.md`), which observed the catalog counting 60 active
entries while `output/portfolio-truth-latest.json` carried 110
declared-active projects, and found 6/7 wave-1 repos "catalog-active but
GitHub-archived."

## Root cause (verified on bytes, not inferred)

The nightly job (`com.d.portfolio-maintenance`, 02:00 local) generates
portfolio-truth from a **separate ref-pinned runtime clone**
(`~/Projects/GithubRepoAuditor-runtime-truth-authority`, pinned via
`EXPECTED_REF` in `~/scripts/portfolio-maintenance.sh`) and writes output
into this dev repo. Timeline for the 2026-07-17 run:

| Time (local) | Event |
|---|---|
| 07-16 22:43 | `fd5d434` — current pinned producer ref (pre-tribunal) |
| 07-17 01:14 | tribunal dispositions merge into this repo's catalog (`9b38914`) |
| 07-17 01:49 | cadence alignment (`b05e150`); catalog now counts **60 active** |
| 07-17 02:00 | nightly run generates from the pinned clone, whose catalog counts **114 active** → truth shows 110 declared-active |

So the discrepancy is not a derivation bug and not a race: the pinned
producer ref predates the tribunal dispositions. The pin is the intended
supply-chain guard (expected-repository + expected-ref verification in the
maintenance script) and behaved correctly; it requires a deliberate advance
after catalog-changing merges.

Consequence worth recording: the atlas's wave-1 judgments consumed the
pre-tribunal truth. Its three "catalog flip" recommendations (da-scaffold,
AIFortuneTeller, WorkdayDebrief) were already satisfied by the tribunal
merge — all three are `lifecycle_state: archived` in the current catalog.
The atlas's GitHub/Notion divergence findings stand.

## Operator action (one line, deliberately not self-applied)

Advance the pin to the post-tribunal head and sync the runtime clone:

```bash
git -C ~/Projects/GithubRepoAuditor-runtime-truth-authority fetch origin \
  && git -C ~/Projects/GithubRepoAuditor-runtime-truth-authority checkout b05e150e0150d3286de653c3647677f535bcddd8 \
  && sed -i '' 's/^EXPECTED_REF=.*/EXPECTED_REF=b05e150e0150d3286de653c3647677f535bcddd8/' ~/scripts/portfolio-maintenance.sh
```

(The runtime clone must contain the ref before the pin advances, hence the
fetch/checkout first. If the tribunal merge has not been pushed to the
runtime clone's origin, push it first — agent branches stay unpushed by
standing rule.)

## Verification

After the next 02:00 run (or a manual `bash ~/scripts/portfolio-maintenance.sh`):
`portfolio-truth-latest.json` declared-active count should drop to ~60 and
`AIFortuneTeller` / `WorkdayDebrief` / `da-scaffold` should read
`declared.lifecycle_state: archived`.

## Process follow-up (optional, separate decision)

Any merge that touches `config/portfolio-catalog.yaml` should carry a
checklist item "advance the runtime-truth-authority pin," or the maintenance
script could emit a loud warning when the dev repo's catalog head is ahead of
the pinned ref. Otherwise every catalog-changing campaign reproduces this
class of stale-truth window.
