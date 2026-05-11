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

## Current analyzer fields (selected)

### ReadmeAnalyzer

In addition to existing README quality fields, `ReadmeAnalyzer` now produces:

- `readme_last_touched_days` — days since the README file was last modified, based on Git history
- `code_last_touched_days` — days since any non-README file in the repo was last modified
- `readme_staleness_ratio` — `readme_last_touched_days / code_last_touched_days`; higher means the README is aging faster than the code
- `readme_stale` — boolean; `true` when `readme_staleness_ratio > 5.0` AND `code_last_touched_days < 90`, i.e., the README is more than five times older than the code and the code is still being actively touched

Excel and control-center surfacing for these staleness fields is deferred to Sprint 2 S2.4; they are present in JSON output today.

### ActivityAnalyzer

`ActivityAnalyzer` now produces release signal fields via `GithubClient.get_releases()`:

- `has_any_release` — boolean; whether the repo has at least one published release
- `release_count` — total number of releases fetched (capped at 10 per run)
- `releases_available` — whether the releases endpoint was reachable
- `latest_release_age_days` — days since the most recent release was published
- `latest_release_is_prerelease` — boolean; whether the most recent release is marked as a pre-release

Excel and control-center surfacing for these release fields is deferred to Sprint 2 S2.4; they are present in JSON output today.

## Keep in mind

- The workbook and HTML surfaces consume the same scored audit facts.
- Prefer additive result fields over renaming existing ones.
- If a new analyzer changes the explanation story, update the explainability surfaces too.
