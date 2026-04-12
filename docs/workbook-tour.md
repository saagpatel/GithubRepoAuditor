# Workbook Tour

## Start here

The workbook is the main operator surface. For most people, this is the best reading order:

1. `Index`
2. `Dashboard`
3. `Run Changes`
4. `Review Queue`
5. `Portfolio Explorer`
6. `Repo Detail`
7. `Executive Summary`

## What each sheet is for

- `Index`: orientation and workbook navigation
- `Dashboard`: portfolio health, operator pressure, and top opportunities
- `Run Changes`: what moved since the last run and whether the movement is good, bad, or worth investigating
- `Review Queue`: what needs action now, why it is in the queue, and what to do next
- `Portfolio Explorer`: cross-repo comparison
- `Repo Detail`: one repo’s score, tier, trend, hotspots, last movement, and next move
- `Executive Summary`: short one-page shareable readout
- `Print Pack`: printer-friendly review surface

## When to use `Run Changes` vs `Review Queue`

- Use `Run Changes` when you want to understand what shifted this run before deciding where to spend time.
- Use `Review Queue` when you are ready to act and need the current blocked, urgent, ready, and safe-to-defer lanes.
- Use `Repo Detail` when one repo from either page needs a deeper decision or a short briefing.

## Hidden sheets

The hidden `Data_*` sheets are the workbook contract. They are intentionally additive and should stay stable because visible sheets and template bindings depend on them.

## Workbook modes

- `standard`: default and safest operational path
- `template`: same facts, but rendered through the committed template shell
