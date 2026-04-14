# Doctor / Release-Check Standard

## Purpose

The doctor/release-check standard defines a minimal validation contract for strategic repos in this portfolio. The goal is to confirm that a repo is in a known-good, runnable state before any significant work session or operator action.

This standard is **advisory-only**. It documents expected commands and patterns — it does not enforce them automatically or widen any automation authority.

## Tiers

### Full Standard (`full`)

Expected for: GithubRepoAuditor, JobCommandCenter, MCPAudit, DecisionStressTest

The full standard requires:

1. **Doctor check** — a command that verifies the project's toolchain, dependencies, and environment are correct. Should exit non-zero if anything is broken.
2. **Release / build check** — a command that confirms the project can produce a clean artifact or pass its full test suite.

### Basic Standard (`basic`)

Expected for: ResumeEvolver

The basic standard requires:

1. **Check command** — a single command that runs linting, type checking, or unit tests. Confirms the project is not in a broken state.

## Stack Patterns

### Python (pytest + ruff)

```bash
# Full standard
python3 -m ruff check src/ tests/
python3 -m pytest -q

# Basic standard
python3 -m ruff check src/ && python3 -m pytest -q
```

### Node.js

```bash
# Full standard
npm run doctor        # custom health-check script
npm run release:check # build + lint + test

# Basic standard
npm run check         # lint + type-check
```

### Tauri 2 (Rust + React/TS)

```bash
# Full standard
npm run check:all     # frontend type-check + Rust cargo check + tests
```

## Tracking

- **`declared.doctor_standard`** — set in `config/portfolio-catalog.yaml` for repos that have adopted the standard (`full` or `basic`). Empty string means no standard is declared.
- **`risk.doctor_gap`** — derived boolean on each truth project. `true` when the repo is in `STRATEGIC_REPOS` but `doctor_standard` is empty, indicating the standard has not yet been declared or adopted.

## Conformance

The doctor/release-check standard is **advisory-only**. No automated remediation or workflow enforcement happens as a result of this standard. The `risk.doctor_gap` flag surfaces in the portfolio risk overlay as a `missing-doctor-standard` risk factor, which contributes to the overall risk tier calculation.

Conformance means: the repo has a working, documented doctor/release-check command, and `doctor_standard` is declared in the catalog.
