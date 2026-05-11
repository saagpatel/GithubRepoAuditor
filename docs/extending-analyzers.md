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

Excel and control-center surfacing for these staleness fields is wired via S2.4.

### ActivityAnalyzer

`ActivityAnalyzer` now produces release signal fields via `GithubClient.get_releases()`:

- `has_any_release` — boolean; whether the repo has at least one published release
- `release_count` — total number of releases fetched (capped at 10 per run)
- `releases_available` — whether the releases endpoint was reachable
- `latest_release_age_days` — days since the most recent release was published
- `latest_release_is_prerelease` — boolean; whether the most recent release is marked as a pre-release

Excel and control-center surfacing for these release fields is wired via S2.4.

## Analyzer Cache Contract

Analyzers can opt in to per-(repo, sha, analyzer) result caching. Cached results are stored in the `analyzer_cache` SQLite table. A cache hit is fully transparent to callers — the framework substitutes the stored result without invoking the analyzer.

### Opting in

Implement `cache_inputs_hash()` on your analyzer class. It must return a stable string hash derived from all inputs that affect the result. Inputs that count as stable:

- Lockfile bytes (content hash, not path)
- README file content + git commit timestamps
- Sorted directory listing + primary language string

Inputs that are **not** stable (do not include): wall-clock time, run-specific IDs, mutable config values.

### Current opt-ins

Three analyzers currently opt in:

- `DependenciesAnalyzer` — hashes lockfile bytes
- `ReadmeAnalyzer` — hashes README content + git timestamps
- `StructureAnalyzer` — hashes sorted directory listing + primary language

### Validating correctness with `--reconcile-cache`

Pass `--reconcile-cache` to re-run all analyzers after the audit with the cache disabled and deep-compare the fresh results against the cached values (1e-6 float tolerance for numeric fields). The run exits non-zero on any divergence and writes `output/cache-reconcile-<user>-<date>.json` with a full diff. This is a CI release-gate tool — not intended for normal runs.

`--no-analyzer-cache` disables the cache for the entire run without the post-run comparison. Use it when you need a guaranteed-fresh pass without the overhead of reconciliation.

## Keep in mind

- The workbook and HTML surfaces consume the same scored audit facts.
- Prefer additive result fields over renaming existing ones.
- If a new analyzer changes the explanation story, update the explainability surfaces too.
