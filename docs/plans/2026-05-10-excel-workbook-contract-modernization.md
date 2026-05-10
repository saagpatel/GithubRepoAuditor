# Excel Workbook Contract Modernization - 2026-05-10

## Status

The first three workbook-surface modernization passes are implemented.

These passes are intentionally behavior-preserving. They move stable workbook structure ownership out of `src/excel_export.py` and into the helper/runtime layer, where workbook ordering, visibility, and finalization helpers already live.

## What Changed

- `src/excel_workbook_helpers.py` now owns `CORE_VISIBLE_SHEETS`.
- `src/excel_export.py` imports and re-exports `CORE_VISIBLE_SHEETS` for compatibility with existing callers.
- `src/workbook_gate.py` now reads `CORE_VISIBLE_SHEETS` from the workbook helper layer instead of the exporter module.
- `src/excel_export_registry_helpers.py` now owns the default runtime wiring for `CORE_VISIBLE_SHEETS` and `DEFAULT_PREFERRED_SHEET_ORDER`.
- `src/excel_export_registry_helpers.py` also owns the default workbook build-step executor wiring.
- `src/excel_export.py` still re-exports the workbook structure constants, but no longer passes them through every runtime build call.
- `tests/test_excel_export_registry_helpers.py` protects the default and explicit runtime structure contracts.
- The exporter still owns workbook build adapters and the public `export_excel(...)` entrypoint.

## Why This Boundary

The Excel surface remains the next visible maintainability hotspot after closure-forecast consolidation. The safest first pass is to move a stable workbook contract, not sheet rendering logic.

This keeps workbook behavior stable while making future cleanup easier:

- workbook structure constants live beside workbook structure helpers,
- the release gate depends on the workbook contract layer,
- the workbook runtime helper owns the default structure wiring,
- the workbook runtime helper owns the default build-step executor wiring,
- and `src/excel_export.py` remains a compatibility facade for existing tests and callers.

## Verification

Completed during this pass:

```bash
python3 -m pytest tests/test_excel_enhanced.py tests/test_workbook_gate.py -q -p no:cacheprovider
ruff check src/excel_export.py src/excel_workbook_helpers.py src/workbook_gate.py tests/test_excel_enhanced.py tests/test_workbook_gate.py
mypy src/excel_export.py src/excel_workbook_helpers.py src/workbook_gate.py --ignore-missing-imports
```

Focused verification for the second pass:

```bash
python3 -m pytest tests/test_excel_export_registry_helpers.py tests/test_excel_enhanced.py tests/test_workbook_gate.py -q -p no:cacheprovider
ruff check src/excel_export.py src/excel_export_registry_helpers.py src/excel_workbook_helpers.py src/workbook_gate.py tests/test_excel_export_registry_helpers.py tests/test_excel_enhanced.py tests/test_workbook_gate.py
mypy src/excel_export.py src/excel_export_registry_helpers.py src/excel_workbook_helpers.py src/workbook_gate.py --ignore-missing-imports
```

Focused verification for the third pass:

```bash
python3 -m pytest tests/test_excel_export_registry_helpers.py tests/test_excel_enhanced.py tests/test_workbook_gate.py -q -p no:cacheprovider
ruff check src/excel_export.py src/excel_export_registry_helpers.py src/excel_workbook_helpers.py src/workbook_gate.py tests/test_excel_export_registry_helpers.py tests/test_excel_enhanced.py tests/test_workbook_gate.py
mypy src/excel_export.py src/excel_export_registry_helpers.py src/excel_workbook_helpers.py src/workbook_gate.py --ignore-missing-imports
```

Closeout verification:

```bash
python3 -m pytest -q -p no:cacheprovider
ruff check src/ tests/
mypy src/excel_export.py src/excel_export_registry_helpers.py src/excel_workbook_helpers.py src/workbook_gate.py --ignore-missing-imports
python3 -m src --help
python3 -m src.cli --help
make workbook-gate
```

The workbook gate's automated checks passed. Manual desktop Excel signoff remains the normal release-only final step.

## Next Step

Continue with small workbook-contract or exporter-adapter moves only when the ownership boundary is obvious. Do not rewrite sheet rendering or workbook generation in a broad pass.
