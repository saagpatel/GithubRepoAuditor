# Workbook Template Maintenance

The Excel workbook now supports two render modes:

- `standard`: uses the stable code-generated workbook path, is the CLI default, and is the recommended automation mode
- `template`: hydrates the committed workbook template in `assets/excel/analyst-template.xlsx`

## Ownership Boundary

Python owns:
- report and warehouse facts
- hidden `Data_*` sheets
- stable table names and column order
- workbook named ranges used for operator KPIs and filters
- template hydration and native sparkline injection
- visible-sheet compatibility rules, including the current Excel-safe pattern of using plain filtered ranges on visible sheets and structured tables only on hidden `Data_*` sheets

The workbook template owns:
- workbook shell and sheet organization
- print layout
- named-range placeholders
- any Excel-authored native objects already present in the template

Template mode and standard mode should now project the same visible top-line facts.
If one mode changes the visible operator or executive story, update the other mode's
tests and verify parity before shipping.

Partial reruns also depend on a compatible full-baseline report. Workbook regeneration can continue from older reports, but targeted or incremental merge paths should only proceed when the stored baseline contract matches the current audit-affecting portfolio context.

## Template-Stable Tables

These tables are part of the workbook contract:
- `tblRepos`
- `tblDimensions`
- `tblLenses`
- `tblHistory`
- `tblTrendMatrix`
- `tblPortfolioHistory`
- `tblRollups`
- `tblReviewTargets`
- `tblSecurityData`
- `tblSecurityControls`
- `tblSecurityProviders`
- `tblSecurityAlerts`
- `tblActions`
- `tblCollections`
- `tblScenarios`
- `tblGovernancePreview`
- `tblCampaigns`
- `tblWriteback`
- `tblReviewHistoryData`

If one of these names or its column order changes, update both:
- the Python workbook builder
- the committed workbook template

## Additive Workbook Rollups

These workbook-only hidden tables are additive and may evolve without changing the
cross-surface operator contract, as long as they continue deriving from shared report
facts:
- `tblOperatorQueueData`
- `tblOperatorRepoRollups`
- `tblMaterialChangeRollups`

## Safe Update Workflow

1. Update the Python data builder first.
2. Regenerate or edit the template only after the hidden-table contract is settled.
3. Re-run workbook tests in both `template` and `standard` modes.
4. Open the generated workbook in Excel desktop and verify the expected workbook behavior.
5. If compatibility changes are required, preserve hidden `Data_*` table contracts and prefer visible-sheet autofilters over visible-sheet structured tables.

## When Python-Only Changes Are Enough

Usually Python-only changes are safe when you:
- add rows within an existing hidden-table contract
- change how a KPI is calculated without renaming the binding
- adjust `standard` mode presentation only

## When Python and Template Changes Are Both Required

Update both when you:
- add or rename template-bound sheets
- rename a stable hidden table
- reorder columns used by workbook bindings
- add or rename named ranges used by the template
