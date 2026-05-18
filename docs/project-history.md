# Project History

This project began as a GitHub repository auditor and grew into a workbook-first portfolio
operator for developers with many projects.

## What Changed Over Time

- The first version focused on cloning repositories, scoring completeness and interest,
  and generating JSON, Markdown, HTML, and workbook reports.
- Later work made the workbook the primary operating surface and aligned the workbook,
  Markdown, HTML, review-pack, control-center, and scheduled-handoff outputs around one
  shared weekly story.
- The operator layer added read-only triage, follow-through tracking, historical state,
  campaign previews, and approval-aware Action Sync guidance while keeping external
  mutation explicit and opt-in.
- The portfolio truth layer added a local workspace snapshot, context-quality signals,
  operating-path guidance, and advisory risk overlays.
- Public-readiness work added GitHub Releases, a self-contained `audit.pyz` artifact,
  clearer install paths, branch protection, and CI that runs for required checks.
- Detailed private planning notes and agent execution plans were later pruned from the
  public documentation tree so current docs remain focused on product usage and
  maintainable architecture.

## Recent Maintenance

- The Security Review workflow remains manual and review-led. Recent security
  maintenance used small pull requests to add or repair repository security controls,
  then refreshed read-only GitHub alert evidence before choosing the next batch.
- The latest CodeQL setup batch added JavaScript/TypeScript analysis to
  `LegalDocsReview`, `IncidentReview`, and `IncidentManagement`. All three default
  branches passed CodeQL after merge and had no open code-scanning alerts in the live
  GitHub alert check.
- `LegalDocsReview` also needed a lockfile refresh because its existing package
  manifest and lockfile were out of sync, which blocked the repo's frozen-lockfile CI
  checks before the CodeQL setup could merge safely.

## Current Documentation Source

Use these files for current behavior:

- [README.md](../README.md)
- [Product modes](modes.md)
- [Architecture](architecture.md)
- [Release gates](release-gates.md)
- [Writeback safety model](writeback-safety-model.md)

Older private planning notes and agent execution plans were removed from the public
documentation tree because they contained local-path, handoff, and worker-instruction
details that were no longer useful for public users. Their project-level lessons have
been folded into the active docs above.
