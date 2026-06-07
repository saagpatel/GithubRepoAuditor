# Machine-Wide Consolidation

This is the operating plan for reducing portfolio-scale attention drag across
`/Users/d/Projects` and adjacent Codex operating repos.

## Current Packet

Run this first in new Codex sessions:

```sh
cd /Users/d/Projects/GithubRepoAuditor
python -m src.codex_restart_packet --workspace-root /Users/d/Projects
```

The packet combines:

- latest `output/portfolio-truth-latest.json`
- live git state for `/Users/d/Projects`
- live git state for adjacent operating repos such as `personal-ops` and
  `.codex/codexkit`
- archive/dependency/temp exclusions so old cleanup waves do not reappear as
  live work

## Consolidation Policy

1. Start from the packet, not from a raw filesystem scan.
2. Treat `.portfolio-noise-archive`, `.claude`, `.codex-maintenance`,
   `.cowork`, `.serena`, dependency directories, build outputs, and
   `evals/fixtures` as excluded unless the task explicitly says archive
   forensics or fixture maintenance.
3. Resolve dirty operating repos before lower-signal product drift. The usual
   operating set is:
   - `/Users/d/.local/share/personal-ops`
   - `/Users/d/.codex/codexkit`
   - `/Users/d/Projects/GithubRepoAuditor`
   - `/Users/d/Projects/PortfolioCommandCenter`
   - `/Users/d/Projects/Notion`
   - `/Users/d/Projects/bridge-db`
   - `/Users/d/Projects/notification-hub`
   - `/Users/d/Projects/mcpforge`
4. Convert broad repo drift into decisions:
   - active now
   - verify and land
   - park with handoff
   - archive/noise
   - external or remote verification needed
5. Keep restart prompts short. Tell the next session to rerun the packet and
   inspect the live repo state, not to inherit stale chat counts.

## 2026-06-07 Baseline

The first verified packet run after adding the restart surface reported:

- portfolio truth generated at `2026-06-07T08:32:03.303071+00:00`
- portfolio truth projects: `129`
- portfolio truth warnings: `1`
- git repos scanned after exclusions: `138`
- dirty repos: `67`
- non-main or detached repos: `35`
- repos without upstream: `20`
- repos ahead or behind upstream: `26`

The top active working set was:

1. `personal-ops`
2. `codexkit`
3. `GithubRepoAuditor`
4. `ITPRJsViaClaude/SlackIncidentBot`
5. `cross-system-smoke`
6. `Fun:GamePrjs/LoreKeeper`
7. `notification-hub`
8. `portfolio-health`
9. `bridge-db`
10. `mcpforge`
11. `Notion`
12. `PortfolioCommandCenter`

These counts are evidence from one run, not a permanent registry. Rerun the
packet before making a new decision.

## Next Strong Lane

Keep `GithubRepoAuditor` as the machine-readable restart surface, then finish
or deliberately park the dirty operating repos it surfaces. Do not chase broad
product drift until the operating layer is verified or explicitly deferred.
