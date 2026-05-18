# Contributing to GitHub Repo Auditor

Thank you for your interest in contributing. This guide covers how to set up a local development environment, run tests, follow coding conventions, add a new analyzer, and submit a pull request.

## Prerequisites

- **Python 3.11 or later** — the codebase uses `match` statements, `X | Y` union syntax, and other 3.11+ features.
- **A GitHub Personal Access Token** — required to audit private repos and avoid rate limits. Create one at <https://github.com/settings/tokens> with `repo` and `read:org` scopes.
- **Git** — standard installation, used for shallow cloning during audits.

## Local Setup

```bash
# Clone the repo
git clone https://github.com/<your-fork>/GithubRepoAuditor.git
cd GithubRepoAuditor

# Install all runtime + dev dependencies
make install-dev

# Copy the environment template and fill in your token
cp .env.example .env
# Edit .env — at minimum set GITHUB_TOKEN=<your token>
```

If you do not use `make`, the equivalent pip command is:

```bash
python3 -m pip install -r requirements.txt pytest ruff mypy
```

## Running Tests

```bash
make test
```

This runs the full test suite under `tests/` with verbose output. The suite covers all 12 analyzers, the scorer, the report generator, the GitHub API client, and the CLI integration.

To run a single test file:

```bash
python3 -m pytest tests/test_scorer.py -v
```

To run tests matching a pattern:

```bash
python3 -m pytest tests/ -k "readme" -v
```

## Linting and Formatting

```bash
# Check for lint errors (does not modify files)
make lint

# Auto-format source and test files
make format
```

Both commands target `src/` and `tests/`. The project uses [Ruff](https://docs.astral.sh/ruff/) configured in `pyproject.toml` with `target-version = "py311"` and `line-length = 100`. Rules `E`, `F`, and `I` (errors, pyflakes, isort) are enabled.

CI will reject PRs that fail `ruff check`. Run `make lint` before opening a PR.

## Type Checking

```bash
make type-check
```

This runs `mypy src/ --ignore-missing-imports`. All new functions must have complete type annotations — no `Any` usage, no untyped parameters.

## Coding Conventions

These conventions come from the project's `CLAUDE.md` and must be followed in all contributions:

- **Type hints on all functions** — parameters and return types, always. Use `from __future__ import annotations` at the top of each module.
- **f-strings** — use f-strings for string interpolation, not `%` formatting or `.format()`.
- **`pathlib` over `os.path`** — use `Path` objects for all file system operations. `os.path.join`, `os.listdir`, etc. are not welcome.
- **`snake_case`** for all file names, function names, and variable names.
- **No PyGithub** — the project intentionally uses raw `requests` calls to the GitHub REST API v3. Do not introduce `PyGithub`, `ghapi`, or any other GitHub client library.
- **No external analysis frameworks** — keep the dependency footprint minimal. Do not add AST analysis libraries, complexity frameworks, or linting engines as runtime dependencies. Pure Python + stdlib is the default; add a dependency only when the value is unambiguous.
- **No hardcoded usernames or tokens** — credentials come from environment variables (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `NOTION_TOKEN`). Usernames come from CLI arguments.
- **No silent error swallowing** — always log or re-raise exceptions. The analyzer pipeline uses `logger.warning(...)` before returning a zero-score fallback result; follow the same pattern.

## Adding a New Analyzer

Analyzers live in `src/analyzers/`. Each one scores a single dimension (0.0–1.0) and returns an `AnalyzerResult`.

### Step 1 — Create the module

Create `src/analyzers/<your_dimension>.py` and implement a class that extends `BaseAnalyzer`:

```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.analyzers.base import BaseAnalyzer
from src.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from src.github_client import GitHubClient


class YourDimensionAnalyzer(BaseAnalyzer):
    name = "your_dimension"
    weight = 0.05  # fraction of overall completeness score

    def analyze(
        self,
        repo_path: Path,
        metadata: RepoMetadata,
        github_client: GitHubClient | None = None,
    ) -> AnalyzerResult:
        score = 0.0
        findings: list[str] = []
        details: dict[str, object] = {}

        # ... scoring logic ...

        return self._result(score, findings, details)
```

`self._result(score, findings, details)` clamps the score to `[0.0, 1.0]` and wraps it in an `AnalyzerResult`. Use it rather than constructing `AnalyzerResult` directly.

### Step 2 — Register the analyzer

Open `src/analyzers/__init__.py` and:

1. Import your new class at the top.
2. Append an instance to `ALL_ANALYZERS`.

```python
from src.analyzers.your_dimension import YourDimensionAnalyzer

ALL_ANALYZERS = [
    ...
    YourDimensionAnalyzer(),
]
```

### Step 3 — Add a weight in the scorer

Open `src/scorer.py` and add your dimension name to the `WEIGHTS` dict. Weights must sum to `1.0` after adding the new entry, so adjust existing weights proportionally.

### Step 4 — Write tests

Add `tests/test_your_dimension.py`. Cover at minimum:

- A repo that scores the maximum (all checks pass).
- A repo that scores zero (no relevant files).
- At least one partial-credit case.

Tests should use real `Path` objects pointing to small fixture directories under `tests/fixtures/`, not mocked file systems.

## Pull Request Checklist

Before opening a PR, verify:

- [ ] `make test` passes with no failures.
- [ ] `make lint` reports no errors.
- [ ] `make type-check` reports no errors (or pre-existing errors only — do not introduce new ones).
- [ ] No hardcoded GitHub usernames or API tokens anywhere in the diff.
- [ ] New analyzer (if any) is registered in `ALL_ANALYZERS` and has a weight in `WEIGHTS`.
- [ ] New tests added for any new public functions or analyzer logic.
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` with a brief description of the change.
- [ ] Commit messages follow conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`.

## Questions

Open an issue or start a discussion on GitHub. Please include the output of `python3 -m src.cli --help` and your Python version (`python3 --version`) when reporting bugs.
