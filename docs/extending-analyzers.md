# Extending Analyzers

## What an analyzer should do

An analyzer should inspect one aspect of a repo and return:
- a dimension name
- a score
- short findings
- any details needed by downstream report surfaces

## Good analyzer additions

- stay focused on one dimension
- return stable fields so reports stay additive
- keep network work minimal
- prefer repo-local evidence first

## Practical workflow

1. Add the analyzer under [/Users/d/Projects/GithubRepoAuditor/src/analyzers](/Users/d/Projects/GithubRepoAuditor/src/analyzers).
2. Make sure it fits the existing result shape used by scoring and report writers.
3. Add tests for both the analyzer output and any score/report behavior it changes.
4. Re-run `pytest` and `make workbook-gate` if workbook-facing summaries change.

## Keep in mind

- The workbook and HTML surfaces consume the same scored audit facts.
- Prefer additive result fields over renaming existing ones.
- If a new analyzer changes the explanation story, update the explainability surfaces too.
