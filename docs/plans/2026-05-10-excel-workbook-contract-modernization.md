# Excel Workbook Contract Modernization - 2026-05-10

## Status

The first workbook-surface modernization pass is implemented.

This pass is intentionally behavior-preserving. It moves the workbook visible-sheet contract out of `src/excel_export.py` and into `src/excel_workbook_helpers.py`, where the workbook ordering and finalization helpers already live.

## What Changed

- `src/excel_workbook_helpers.py` now owns `CORE_VISIBLE_SHEETS`.
- `src/excel_export.py` imports and re-exports `CORE_VISIBLE_SHEETS` for compatibility with existing callers.
- `src/workbook_gate.py` now reads `CORE_VISIBLE_SHEETS` from the workbook helper layer instead of the exporter module.
- The exporter still owns workbook build adapters and the public `export_excel(...)` entrypoint.

## Why This Boundary

The Excel surface remains the next visible maintainability hotspot after closure-forecast consolidation. The safest first pass is to move a stable workbook contract, not sheet rendering logic.

This keeps workbook behavior stable while making future cleanup easier:

- workbook structure constants live beside workbook structure helpers,
- the release gate depends on the workbook contract layer,
- and `src/excel_export.py` remains a compatibility facade for existing tests and callers.

## Verification

Completed during this pass:

```bash
python3 -m pytest tests/test_excel_enhanced.py tests/test_workbook_gate.py -q -p no:cacheprovider
ruff check src/excel_export.py src/excel_workbook_helpers.py src/workbook_gate.py tests/test_excel_enhanced.py tests/test_workbook_gate.py
mypy src/excel_export.py src/excel_workbook_helpers.py src/workbook_gate.py --ignore-missing-imports
```

Closeout verification:

```bash
python3 -m pytest -q -p no:cacheprovider
ruff check src/ tests/
mypy src/excel_export.py src/excel_workbook_helpers.py src/workbook_gate.py --ignore-missing-imports
python3 -m src --help
python3 -m src.cli --help
make workbook-gate
```

The workbook gate's automated checks passed. Manual desktop Excel signoff remains the normal release-only final step.

## Next Step

Continue with small workbook-contract or exporter-adapter moves only when the ownership boundary is obvious. Do not rewrite sheet rendering or workbook generation in a broad pass.
