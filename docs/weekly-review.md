# Weekly Review

## How to review your portfolio in 5 minutes

1. Run `audit <github-username> --doctor` to catch setup or baseline issues first.
2. Run `audit <github-username> --html` to generate the current workbook and dashboard.
3. Run `audit <github-username> --control-center` to refresh the operator queue.
4. Open the workbook and move in this order:
   - `Dashboard` for the big picture
   - `Run Changes` for what moved this run and whether the movement is healthy or concerning
   - `Review Queue` for what needs action now and the exact next step
   - `Repo Detail` for a single-repo briefing
   - `Executive Summary` when you need a short shareable readout

## Recommended cadence

- Start with anything in `Blocked`
- Use `Run Changes` before `Review Queue` when you want to understand what changed instead of jumping straight into action
- Clear `Needs Attention Now` before lower-pressure work
- Use `Repo Detail` when one repo needs a deeper decision
- Leave `Safe to Defer` alone unless priorities changed

## Operator focus reading order

Primary workbook, HTML, Markdown, and review-pack surfaces now compress the deeper follow-through model into five buckets:

1. `Act Now` for blocked or urgent operator pressure
2. `Watch Closely` for active items that need more evidence but do not yet outrank the rest
3. `Improving` for paths that are stabilizing and rebuilding trust
4. `Fragile` for progress that is real but still easy to lose
5. `Revalidate` for items that still need confidence rebuilt before they can be treated as restored

Read those buckets in exactly that order on the primary surfaces. The hidden workbook data and raw JSON still keep the richer lifecycle detail underneath.

## When to run workbook gate

Use `make workbook-gate` only when you changed workbook-facing code or layout. The normal audit workflow does not require the gate every time.
