# Closure Forecast Modernization - 2026-05-09

## Status

The first five closure-forecast modernization passes are implemented.

These passes are intentionally behavior-preserving. The first pass added conceptual facade modules for the sprawling `operator_trend_closure_forecast_*` helper family and routed `operator_resolution_trend.py` through those facades. The second pass moved the core implementation behind the core facade. The third pass moved the freshness implementation behind the freshness controls facade. The fourth pass moved the reacquisition implementation behind the reacquisition controls facade. The fifth pass moved the reset-family implementation behind the reset controls facade. Existing module paths remain importable.

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

Third-pass implementation move:

- `src/operator_trend_closure_forecast_freshness_controls.py` now owns freshness, evidence, decay, and freshness-hotspot helpers.
- `src/operator_trend_closure_forecast_freshness.py` is a compatibility wrapper.
- Existing freshness, reacquisition, reset-reentry freshness, and facade tests still cover old import paths.

Fourth-pass implementation move:

- `src/operator_trend_closure_forecast_reacquisition_controls.py` now owns reacquisition, refresh recovery, persistence, churn, reacquisition freshness, and persistence-reset helpers.
- `src/operator_trend_closure_forecast_reacquisition.py` and `src/operator_trend_closure_forecast_reacquisition_freshness.py` are compatibility wrappers.
- Existing reacquisition, reacquisition freshness, and facade tests still cover old import paths.

Fifth-pass implementation move:

- `src/operator_trend_closure_forecast_reset_controls.py` now owns reset refresh, reset reentry freshness, reset reentry rebuild, rebuild freshness, rebuild persistence, reentry restore, rerestore, and rererestore helpers.
- The old reset-family modules are compatibility wrappers.
- Existing reset-family and facade tests still cover old import paths.

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

Completed during the third freshness consolidation pass:

```bash
python3 -m pytest tests/test_operator_trend_closure_forecast_freshness.py tests/test_operator_trend_closure_forecast_reacquisition.py tests/test_operator_trend_closure_forecast_reacquisition_freshness.py tests/test_operator_trend_closure_forecast_reset_reentry_freshness.py tests/test_operator_trend_closure_forecast_facades.py -q -p no:cacheprovider
ruff check src/operator_trend_closure_forecast_freshness.py src/operator_trend_closure_forecast_freshness_controls.py tests/test_operator_trend_closure_forecast_freshness.py tests/test_operator_trend_closure_forecast_facades.py
mypy src/operator_trend_closure_forecast_freshness.py src/operator_trend_closure_forecast_freshness_controls.py --ignore-missing-imports
```

Completed during the fourth reacquisition consolidation pass:

```bash
python3 -m pytest tests/test_operator_trend_closure_forecast_reacquisition.py tests/test_operator_trend_closure_forecast_reacquisition_freshness.py tests/test_operator_trend_closure_forecast_facades.py -q -p no:cacheprovider
ruff check src/operator_trend_closure_forecast_reacquisition.py src/operator_trend_closure_forecast_reacquisition_freshness.py src/operator_trend_closure_forecast_reacquisition_controls.py tests/test_operator_trend_closure_forecast_reacquisition.py tests/test_operator_trend_closure_forecast_reacquisition_freshness.py tests/test_operator_trend_closure_forecast_facades.py
mypy src/operator_trend_closure_forecast_reacquisition.py src/operator_trend_closure_forecast_reacquisition_freshness.py src/operator_trend_closure_forecast_reacquisition_controls.py --ignore-missing-imports
```

Completed during the fifth reset-family consolidation pass:

```bash
python3 -m pytest tests/test_operator_trend_closure_forecast_reset_refresh.py tests/test_operator_trend_closure_forecast_reset_reentry_freshness.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_freshness.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_persistence.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_freshness.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore_rererestore_persistence.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_recovery.py tests/test_operator_trend_closure_forecast_reset_reentry_rebuild_reentry_restore_rerererestore_persistence.py tests/test_operator_trend_closure_forecast_facades.py -q -p no:cacheprovider
ruff check src/operator_trend_closure_forecast_reset*.py tests/test_operator_trend_closure_forecast_reset*.py tests/test_operator_trend_closure_forecast_facades.py
mypy src/operator_trend_closure_forecast_reset*.py --ignore-missing-imports
```

## Next Consolidation Step

The closure-forecast implementation bodies now sit behind the four conceptual facade modules. The next cleanup pass can either keep this compatibility state stable while downstream callers settle, or do a separate retire-old-wrapper audit once import usage proves the wrappers are no longer needed.
