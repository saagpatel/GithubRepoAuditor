# Weekly Review

## How to review your portfolio in 5 minutes

1. Run `audit <github-username> --doctor` to catch setup or baseline issues first.
2. Run `audit <github-username> --html` to generate the current workbook and dashboard.
3. Run `audit <github-username> --control-center` to refresh the operator queue.
4. Open the workbook and move in this order:
   - `Dashboard` for the big picture
   - `Run Changes` for what moved this run
   - `Review Queue` for what needs action now
   - `Repo Detail` for a single-repo briefing
   - `Executive Summary` when you need a short shareable readout

## Recommended cadence

- Start with anything in `Blocked`
- Clear `Needs Attention Now` before lower-pressure work
- Use `Repo Detail` when one repo needs a deeper decision
- Leave `Safe to Defer` alone unless priorities changed

## When to run workbook gate

Use `make workbook-gate` only when you changed workbook-facing code or layout. The normal audit workflow does not require the gate every time.
