# Product Modes

GitHub Repo Auditor now works best when you think about it as one operating system with four product modes. The flags stay the same underneath; this guide is the shared map for the docs, CLI help, workbook, HTML, Markdown, and review-pack wording.

## First Run

Use this mode when you are setting the system up or coming back after a long gap.

Recommended path:

```bash
audit <github-username> --doctor
audit <github-username> --html
audit <github-username> --control-center
```

Goal:
- confirm setup and baseline health
- generate the main workbook and dashboard artifacts
- get the first read-only operator queue

## Weekly Review

Use this mode for the normal ongoing operator loop.

Recommended path:

```bash
audit <github-username> --html
audit <github-username> --control-center
```

Goal:
- refresh the portfolio story
- read the workbook in order
- decide what needs attention now versus what can safely wait

Primary reading order:
- `Dashboard`
- `Run Changes`
- `Review Queue`
- `Portfolio Explorer`
- `Repo Detail`
- `Executive Summary`

## Deep Dive

Use this mode when one repo needs a real decision instead of a quick portfolio pass.

Typical clues:
- the repo keeps resurfacing
- one implementation hotspot dominates the next move
- the maturity gap is still unclear

Best surfaces:
- `Repo Detail`
- implementation hotspots / `Where To Start`
- scorecard and maturity gap lines
- follow-through checkpoint and operator focus lines

## Action Sync

Use this mode only after the local workbook and control-center story is already settled.

Typical flags:

```bash
audit <github-username> --campaign <name> --writeback-target github
audit <github-username> --campaign <name> --writeback-target all --github-projects
```

Goal:
- preview or apply managed campaign actions
- sync to GitHub, GitHub Projects, or Notion
- keep the local report authoritative while mirroring the decision outward

## Default guidance

- `--doctor` is the recommended first step.
- `--excel-mode standard` is the default and recommended workbook path.
- `--control-center` is the read-only daily operator entrypoint.
- `template` workbook mode, scorecards config, catalog config, campaigns, writeback, GitHub Projects, and Notion sync are advanced workflows.
