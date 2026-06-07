# Codex Restart Packet

The restart packet is the compact handoff surface for portfolio-scale Codex
sessions. It combines the latest portfolio truth snapshot with live local git
drift, while excluding archive, dependency, fixture, and temporary surfaces that
should not pull operator attention during normal restarts.

## Command

```sh
python -m src.codex_restart_packet --workspace-root /Users/d/Projects
```

Use JSON when another tool should consume the result:

```sh
python -m src.codex_restart_packet --workspace-root /Users/d/Projects --json
```

## What It Decides

- which repos are dirty, off-main, missing upstream, or ahead/behind upstream
- which operating repos should stay in the active working set even when broad
  product repos are noisy
- whether the canonical `output/portfolio-truth-latest.json` is present and
  fresh enough to trust as the portfolio context layer
- which archive/dependency/temp directories were intentionally ignored

## Default Exclusions

Normal restart scans exclude generated or attention-draining surfaces such as:

- `.portfolio-noise-archive`
- `.claude`
- `.codex-maintenance`
- `.cowork`
- `.serena`
- `.build`, `.derivedData`, `DerivedData`
- `.venv`, `venv`, `node_modules`, `.next`, `dist`, `build`, `target`
- `evals/fixtures`

Inspect these only during an explicit archive-forensics or fixture-maintenance
task.

## Operating Rule

Use this packet before broad cleanup work. If it says an operating repo such as
`personal-ops`, `.codex/codexkit`, `GithubRepoAuditor`, `Notion`, `bridge-db`,
`notification-hub`, `PortfolioCommandCenter`, or `mcpforge` is dirty, resolve or
verify that lane before chasing lower-signal product drift.
