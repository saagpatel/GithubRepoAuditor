# Phase 101 Closeout: Approval Follow-Up Foundation

## Review Of What Was Built

- extended [`src/approval_ledger.py`](/Users/d/Projects/GithubRepoAuditor/src/approval_ledger.py) so approval workflow rows now carry additive approval freshness facts without changing the existing `approval_state` contract:
  - `last_reviewed_at`
  - `last_reviewed_by`
  - `follow_up_cadence_days`
  - `next_follow_up_due_at`
  - `follow_up_state`
  - `follow_up_summary`
  - `stale_approval`
  - `follow_up_command`
- added append-only recurring follow-up persistence in [`src/warehouse.py`](/Users/d/Projects/GithubRepoAuditor/src/warehouse.py) through the new `approval_followup_events` table instead of overwriting the original approval record for the same unchanged fingerprint
- added distinct local-only recurring review commands in [`src/cli.py`](/Users/d/Projects/GithubRepoAuditor/src/cli.py):
  - `--review-governance --governance-scope <scope>`
  - `--review-packet --campaign <name>`
- kept the top-level approval bundle stable while extending it with additive packaging buckets:
  - `top_overdue_approval_followups`
  - `top_due_soon_approval_followups`
- pushed the new approval freshness story through the shared shipped surfaces:
  - [`src/weekly_packaging.py`](/Users/d/Projects/GithubRepoAuditor/src/weekly_packaging.py)
  - [`src/report_enrichment.py`](/Users/d/Projects/GithubRepoAuditor/src/report_enrichment.py)
  - [`src/operator_control_center.py`](/Users/d/Projects/GithubRepoAuditor/src/operator_control_center.py)
  - [`src/operator_snapshot_packaging.py`](/Users/d/Projects/GithubRepoAuditor/src/operator_snapshot_packaging.py)
  - [`src/excel_export.py`](/Users/d/Projects/GithubRepoAuditor/src/excel_export.py)
- widened workbook-visible and hidden approval ledger output so workbook users can see follow-up freshness directly on the `Approval Ledger` sheet and in `Data_ApprovalLedger`
- strengthened regression coverage across approval persistence, CLI hardening, weekly packaging, docs, and workbook-facing approval surfaces in:
  - [`tests/test_approval_ledger.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_approval_ledger.py)
  - [`tests/test_warehouse.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_warehouse.py)
  - [`tests/test_cli_hardening.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_cli_hardening.py)
  - [`tests/test_weekly_packaging.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_weekly_packaging.py)
  - [`tests/test_phase93_approval_surfaces.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_phase93_approval_surfaces.py)
  - [`tests/test_phase93_approval_docs.py`](/Users/d/Projects/GithubRepoAuditor/tests/test_phase93_approval_docs.py)

## Cleanup Review

- kept the original `approval_records` primary key and approval capture semantics intact; the phase avoided a broad approval storage rewrite
- kept approval validity and approval freshness separate:
  - `approval_state` still describes approval validity and apply posture
  - `follow_up_state` now carries recurring local review freshness
- kept `weekly_story_v1` as the only weekly authority and did not introduce a second weekly approval section
- kept `operator_queue`, `primary_target`, and `what_to_do_this_week` unchanged; approval-aware scheduling remains deferred to Phase 102
- did not add new write authority, auto-apply behavior, pytest configuration churn, or CI churn

## Verification Summary

- targeted approval and parity checks:
  - `pytest -q tests/test_approval_ledger.py tests/test_warehouse.py tests/test_weekly_packaging.py tests/test_weekly_story.py tests/test_phase93_approval_surfaces.py tests/test_cli_hardening.py`
  - `pytest -q tests/test_phase93_approval_docs.py tests/test_phase93_approval_surfaces.py tests/test_approval_ledger.py tests/test_weekly_packaging.py tests/test_cli_hardening.py tests/test_warehouse.py`
- full repo gates:
  - `python3 -m ruff check src tests`
  - `pytest -q`
  - `make workbook-gate`
- results:
  - lint passed
  - full repo tests passed: `755 passed`
  - workbook gate automated checks passed
  - manual desktop Excel signoff remains pending because this environment cannot perform the external desktop Excel-open checklist

## Shipped Summary

Phase 101 leaves the repo with a durable approval follow-up foundation instead of a one-shot approval memory model. Initial approval capture remains local-only and unchanged, recurring follow-up review is now tracked append-only, and shipped approval surfaces can distinguish “still approved but due for local review” from “needs reapproval” without widening command authority.

## Next Phase

### Phase 102: Approval-Aware Weekly Scheduling

Objective:
- add one bounded weekly scheduling overlay that uses the new tracked approval freshness facts inside the existing `weekly_story_v1` contract without creating a second recommendation engine

Why it is next:
- approval follow-up timing is now real tracked data instead of inferred prose
- the weekly packaging seam already exists
- the operator core and approval surfaces are now safer places to consume one shared scheduling overlay

Main work:
- extend [`src/weekly_packaging.py`](/Users/d/Projects/GithubRepoAuditor/src/weekly_packaging.py) so weekly approval evidence can influence section emphasis and next-step wording through one explicit overlay
- keep the overlay bounded to weekly packaging and approval packaging rather than rewriting:
  - `operator_queue`
  - `primary_target`
  - `what_to_do_next`
- make approval timing compete only where it should:
  - overdue follow-up should matter more than due-soon follow-up
  - approval timing should not outrank stronger blocked or urgent portfolio pressure
- preserve read-only posture by surfacing guidance and command hints only; no new authority should be added

Main risks:
- accidentally creating a second weekly priority engine outside `weekly_story_v1`
- letting approval timing outrank more important blocked or urgent pressure
- widening the phase into queue-model or operator-core rewrites

Verification expectations:
- add precedence tests proving approval-aware scheduling never outranks stronger blocked or urgent pressure
- add cross-surface parity tests across workbook, Markdown, HTML, review-pack, and scheduled handoff
- run `python3 -m ruff check src tests`
- run `pytest -q`
- run `make workbook-gate`
- complete the manual desktop Excel signoff because workbook-visible weekly wording is likely to change again

## Remaining Roadmap

- No later phases remain in the active 98-102 roadmap after Phase 102.
