# AGENTS.md - GithubRepoAuditor Source

## Review guidelines

Treat source changes as portfolio-truth contract changes when they affect
`output/portfolio-truth-latest.json`, operator queues, generated workbooks,
dashboards, badges, Markdown reports, or seam-linter results. Review for stale
state reporting, generated-vs-canonical confusion, dropped provenance markers,
schema drift, and fields that make parked, archived, experiment, or held work
look active.

Mutation boundaries are merge-relevant. Review `auto_apply`, `ops_writeback`,
GitHub clients, Notion sync/export code, automation executors, and approval
ledger paths for dry-run preservation, explicit target selection, idempotent
recovery, and no silent external writes.

Exact output matters. If CLI JSON, workbook columns, Markdown headings,
operator queue fields, or report sections change, require tests or fixtures
that pin the intended contract and update docs that cite the old shape.
