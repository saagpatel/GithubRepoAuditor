# Closure Forecast Modernization - 2026-05-09

## Status

The first two closure-forecast modernization passes are implemented.

These passes are intentionally behavior-preserving. The first pass added conceptual facade modules for the sprawling `operator_trend_closure_forecast_*` helper family and routed `operator_resolution_trend.py` through those facades. The second pass moved the core implementation behind the core facade. Existing module paths remain importable.

## What Changed

New facade modules:

- `src/operator_trend_closure_forecast_core.py` for events, history, and reweighting helpers.
- `src/operator_trend_closure_forecast_freshness_controls.py` for freshness and evidence helpers.
- `src/operator_trend_closure_forecast_reacquisition_controls.py` for reacquisition and refresh helpers.
- `src/operator_trend_closure_forecast_reset_controls.py` for reset, reentry, rebuild, restore, and rerestore helpers.

`src/operator_resolution_trend.py` now imports closure-forecast helpers from those conceptual modules instead of importing directly from each long lifecycle-stage module.

Second-pass implementation move:

- `src/operator_trend_closure_forecast_core.py` now owns the events, history, and reweighting implementation.
- `src/operator_trend_closure_forecast_events.py`, `src/operator_trend_closure_forecast_history.py`, and `src/operator_trend_closure_forecast_reweighting.py` are compatibility wrappers.
- Existing tests still import the old modules, and facade tests verify old and new import surfaces resolve to the same functions.

## Compatibility Rule

Do not remove the original `operator_trend_closure_forecast_*` modules in this pass. They are still the compatibility import surface for tests and any downstream callers.

Future consolidation may move implementation bodies behind the facade modules, but only after:

1. old imports are covered by compatibility tests,
2. full pytest and Ruff pass,
3. scoped mypy stays green or has a documented pre-existing advisory failure,
4. CLI help smoke checks pass,
5. and workbook gate passes.

## Verification

Completed during this pass:

```bash
python3 -m pytest tests/test_operator_trend_closure_forecast*.py -q -p no:cacheprovider
ruff check src/operator_resolution_trend.py src/operator_trend_closure_forecast_*controls.py src/operator_trend_closure_forecast_core.py tests/test_operator_trend_closure_forecast_facades.py
python3 -m src --help
python3 -m src.cli --help
python3 -m pytest -q -p no:cacheprovider
ruff check src/ tests/
mypy src/operator_resolution_trend.py src/operator_trend_closure_forecast_core.py src/operator_trend_closure_forecast_freshness_controls.py src/operator_trend_closure_forecast_reacquisition_controls.py src/operator_trend_closure_forecast_reset_controls.py --ignore-missing-imports
make workbook-gate
```

Required tests and Ruff passed. Scoped mypy passed for the changed closure-forecast surface. Repo-wide `mypy src/ --ignore-missing-imports` remains advisory and still fails on the pre-existing type backlog outside this change area. Workbook gate automated checks passed and still require manual desktop Excel signoff for release.

Completed during the second core consolidation pass:

```bash
python3 -m pytest tests/test_operator_trend_closure_forecast_events.py tests/test_operator_trend_closure_forecast_history.py tests/test_operator_trend_closure_forecast_reweighting.py tests/test_operator_trend_closure_forecast_facades.py -q -p no:cacheprovider
ruff check src/operator_trend_closure_forecast_core.py src/operator_trend_closure_forecast_events.py src/operator_trend_closure_forecast_history.py src/operator_trend_closure_forecast_reweighting.py tests/test_operator_trend_closure_forecast_events.py tests/test_operator_trend_closure_forecast_history.py tests/test_operator_trend_closure_forecast_reweighting.py tests/test_operator_trend_closure_forecast_facades.py
mypy src/operator_trend_closure_forecast_core.py src/operator_trend_closure_forecast_events.py src/operator_trend_closure_forecast_history.py src/operator_trend_closure_forecast_reweighting.py --ignore-missing-imports
```

## Next Consolidation Step

The next pass can move the freshness implementation behind `operator_trend_closure_forecast_freshness_controls.py`. Keep the old `operator_trend_closure_forecast_freshness.py` module as a compatibility wrapper until all downstream callers are migrated or explicitly retired.
