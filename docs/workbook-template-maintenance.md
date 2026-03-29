# Workbook Template Maintenance

The Excel workbook now has two modes:
- `template` (default): hydrates the committed workbook template at `assets/excel/analyst-template.xlsx`
- `standard`: uses the fallback code-generated workbook path

## Ownership Boundary

Python owns:
- report and warehouse facts
- hidden `Data_*` sheets
- stable Excel table names and column order
- named ranges used for top-level workbook KPIs
- output workbook hydration and save flow

The workbook template owns:
- pivot tables
- slicers
- native sparkline groups
- print layouts
- executive presentation formatting

## Template-Stable Table Contracts

These tables are intended to stay stable for the template:
- `tblRepos`
- `tblDimensions`
- `tblLenses`
- `tblHistory`
- `tblSecurity`
- `tblActions`
- `tblCollections`
- `tblScenarios`
- `tblTrendMatrix`
- `tblPortfolioHistory`
- `tblRollups`
- `tblReviewTargets`

If one of these names or its column order changes, update both:
- the Python workbook builder
- the template workbook bindings

## Safe Update Workflow

1. Update the Python workbook data builder first.
2. Regenerate or edit the template only after the new hidden table contract is final.
3. Re-run the Excel tests, especially template-mode integrity checks.
4. Open the generated workbook in Excel desktop and confirm:
   - pivots still point at the expected hidden tables
   - slicers still work
   - native sparkline groups still render
   - executive sheets still print correctly

## When You Need Both Python and Template Edits

Make changes in both places when you:
- rename a hidden sheet
- rename a stable table
- reorder or rename columns used by pivots or sparklines
- add new executive workbook KPIs that depend on named ranges
- move template-owned objects to different sheets

## When Python-Only Changes Are Usually Enough

Usually you only need Python changes when you:
- add data rows within an existing contract
- change calculations behind an existing KPI
- adjust workbook facts without renaming bound tables or ranges
- use `standard` mode only for debugging or CI output
