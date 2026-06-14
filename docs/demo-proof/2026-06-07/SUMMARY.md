# PortfolioCommandCenter Demo Proof Package

This package proves the 2026-06-07 local five-tab PortfolioCommandCenter demo.
GithubRepoAuditor is the evidence producer because it owns the portfolio truth
and generated screenshots; PortfolioCommandCenter is the subject repo being
demonstrated.

Status: passed.

Historical proof points from the captured 2026-06-07 run:

- Portfolio tab: 129 projects.
- Risk + Security tab: 117 scanned repos and 63 with open high/critical alerts.
- Burndown tab: advisory-grouped fix guidance.
- Trends tab: risk and high/critical history charts.
- Weekly Digest tab: current decision ends with `Start with codexkit.`

For current live private portfolio counts, query the canonical generated
snapshot instead of reusing this historical proof summary:

```sh
jq '{generated_at,total:(.projects|length),counts:.source_summary.attention_state_counts}' output/portfolio-truth-latest.json
```

Use `proof-package.json` for the machine-readable claim-to-evidence map and
`README.md` for the narrative proof summary.
