# Closure Forecast Wrapper Retirement Audit - 2026-05-10

## Status

Do not retire the closure-forecast compatibility wrappers yet.

The closure-forecast implementation bodies now sit behind the conceptual facade modules, and production code imports those facades. The original long `operator_trend_closure_forecast_*` module paths remain useful as a compatibility contract and are still deliberately exercised by tests.

## Evidence

Audit scope:

- Repo-local Python imports in `src/` and `tests/`.
- Local `/Users/d/Projects` text search for old closure-forecast wrapper names outside this repo.
- Current modernization record in `docs/plans/2026-05-09-closure-forecast-modernization.md`.

Findings:

- Product code has no imports from old closure-forecast wrapper modules.
- `src/operator_resolution_trend.py` imports closure-forecast helpers from the facade modules.
- Tests still include 24 old-path imports across 17 test files.
- Local `/Users/d/Projects` search found 0 old closure-forecast wrapper references outside `GithubRepoAuditor`.
- The wrapper modules themselves remain the repo's stable compatibility surface.

## Decision

Keep all compatibility wrappers for now.

Do not remove the old module paths in a cleanup pass unless a future audit also updates or retires the old-path compatibility tests and explicitly accepts the downstream compatibility break.

## Retirement Gate

Wrapper removal is safe only after all of these are true:

1. No product code imports old wrapper modules.
2. No repo tests require old wrapper imports as a compatibility guarantee.
3. A local workspace search finds no downstream callers outside this repo.
4. The repo docs explicitly announce the compatibility removal.
5. Full pytest, Ruff, scoped mypy, CLI help smokes, and workbook gate pass after removal.

## Recommended Next Move

Leave the wrappers in place. If more modernization is useful, apply the same behavior-preserving facade pattern to a different high-sprawl area instead of deleting this compatibility layer now.
