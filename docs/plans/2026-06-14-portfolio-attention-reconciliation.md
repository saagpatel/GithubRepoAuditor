# Portfolio Attention Reconciliation - 2026-06-14

## Scope

This note records the narrow truth update from the 2026-06-14 portfolio attention reconciliation. It is not a broad portfolio refresh and does not reactivate parked, archived, experiment, evidence-history, or manual-only projects.

## Changes

- `bridge-db` is cataloged as `infrastructure` so generated portfolio truth resolves it as `active-infra`. Its repo-local docs still define it as scope-closed steady maintenance, so weekly attention should surface only concrete bridge, sync, health, or cross-system state decisions.
- `notification-hub` is cataloged as `infrastructure` so generated portfolio truth resolves it as `active-infra`. Runtime or operator-signal claims still require fresh read-only verification before they drive work.
- `AIGCCore` repo-local canonical paths were aligned to `/Users/d/Projects/MoneyPRJsViaGPT/AIGCCore`, matching the live checkout and the portfolio truth path.

## Deferred Decisions

- `AIGCCore` remains active infrastructure. The snapshot's Notion advisory still says `Archive` / `Archived`, but archiving or changing lifecycle/disposition requires explicit operator approval.
- `personal-ops` remains supplementary registry evidence, not a first-class portfolio truth row. Adding it to portfolio truth requires explicit operator approval because it lives outside `/Users/d/Projects` and would widen the registry contract.

## Verification

The normal publish command should be used when Notion context is available:

```sh
uv run python -m src.cli report saagpatel --portfolio-truth
```

Then confirm:

```sh
jq -r '.projects[] | select(.identity.display_name as $n | ["bridge-db","notification-hub","AIGCCore"] | index($n)) | [.identity.display_name,.declared.category,.derived.attention_state,.advisory.notion_portfolio_call,.advisory.notion_current_state] | @tsv' output/portfolio-truth-latest.json
jq '.warnings' output/portfolio-truth-latest.json
```

Expected state:

- `bridge-db`: `category=infrastructure`, `attention_state=active-infra`
- `notification-hub`: `category=infrastructure`, `attention_state=active-infra`
- `AIGCCore`: remains `active-infra`; archive advisory remains deferred

## 2026-06-14 Verification Result

- `uv run python -m src.cli report saagpatel --portfolio-truth` was attempted but refused to publish because `NOTION_TOKEN` was not present and the current `output/portfolio-truth-latest.json` has 137 Notion context rows. The canonical latest snapshot was not replaced.
- A non-publishing build with `include_notion=False` validated the catalog logic: `bridge-db`, `notification-hub`, and `AIGCCore` all resolved to `category=infrastructure` and `attention_state=active-infra`; snapshot validation reported no warnings.
- `uv run pytest -q tests/test_portfolio_truth.py tests/test_catalog_validator.py`: 56 passed, 1 deprecation warning from a legacy CLI invocation test.
- `uv run ruff check .`: passed.
- AIGCCore path cleanup was checked with `rg -n "/Users/d/Projects/AIGCCore" /Users/d/Projects/MoneyPRJsViaGPT/AIGCCore/AGENTS.md`; no stale matches remained.

## 2026-06-19 Publish Result

- `uv run python -m src.cli report saagpatel --portfolio-truth` was rerun after Notion context became available.
- The regenerated latest snapshot preserved `source_summary.notion_context_rows=137`, reported `warnings=[]`, and was generated at `2026-06-19T04:36:19.383106+00:00`.
- `bridge-db`: `category=infrastructure`, `attention_state=active-infra`, `notion_current_state=Shipped`.
- `notification-hub`: `category=infrastructure`, `attention_state=active-infra`, `notion_current_state=Shipped`.
- `uv run pytest -q tests/test_portfolio_truth.py tests/test_catalog_validator.py`: 56 passed, 1 deprecation warning from a legacy CLI invocation test.
- `uv run ruff check .`: passed.
