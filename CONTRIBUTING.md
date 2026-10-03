# Contributing to GitHub Repo Auditor

Thank you for your interest in contributing. This guide covers how to set up a local development environment, run tests, follow coding conventions, add a new analyzer, and submit a pull request.

## Prerequisites and local setup

Use Git, `uv`, and Python 3.11 or later. The checked-in `.python-version` selects
3.11.15 for the locked local/Cloud environment. Run commands from the repository
root; `uv` creates a project virtual environment and can download the selected
interpreter and dependencies during setup. No GitHub, Anthropic, or Notion token
is needed for the fixture checks below. Do not copy credential-bearing `.env`
files into a verification checkout.

```bash
git clone https://github.com/<your-fork>/GithubRepoAuditor.git
cd GithubRepoAuditor
uv sync --locked --extra dev --extra serve --extra config
```

The `serve` extra is needed by web-route tests. `semantic` adds heavyweight ML
and SQLite vector dependencies and remains opt-in for routine local checks.
The older `make install-dev` / pip equivalent installs only `dev,config`, so it
does not provision the full CI test environment.

## Safe smoke and focused tests

```bash
uv run --locked python -m github_repo_auditor.cli --help
uv run --locked --extra dev --extra serve --extra config pytest tests/test_scorer.py -q -p no:cacheprovider
```

The scorer tests use synthetic metadata and block live scorecard lookup. Replace
the test path with the focused fixture tests for your changed module after
checking their prerequisites. CLI help is not a live audit.

For report/export changes, generate the committed demo in a disposable checkout:

```bash
uv run --locked --extra config python scripts/build_demo_artifacts.py
```

This uses `fixtures/demo/sample-report.json` and regenerates only `output/demo/`,
including replacement of older demo artifacts. It does not audit the workstation
or contact provider accounts. Live `audit run`, portfolio-truth regeneration,
seam identity-resolution, writeback, and deployment commands belong to explicit
operator tasks, not a fixture verification pass.

## Broader checks and optional lanes

The lightweight local/Cloud suite excludes the optional semantic-index module:

```bash
uv run --locked --extra dev --extra serve --extra config pytest tests/ -q -p no:cacheprovider -k 'not semantic_index'
uv run --locked --extra dev ruff check src/ tests/
uv run --locked --extra dev ruff format --check src/ tests/
```

`ruff format --check` is read-only; omit `--check` only when deliberately
formatting source. Ruff's actual settings are in `pyproject.toml`.

[GitHub CI](.github/workflows/ci.yml) runs the full suite with `dev,serve,semantic`
on Python 3.11 and 3.12. To reproduce that lane locally, include the semantic
extra explicitly:

```bash
uv run --locked --extra dev --extra serve --extra semantic --extra config pytest tests/ -q -p no:cacheprovider
```

CI type-checks the operator-trend modules listed in that workflow. The broader
`make type-check` target runs `mypy src/ --ignore-missing-imports`; it is a
separate whole-source diagnostic, not a claim that CI checks every module.
For wheel/sdist packaging, install the `build` extra and run
`uv run --locked --extra build python -m build`; this writes local `dist/`
artifacts and does not publish them. Mutation testing, workbook checks and
release-specific prerequisites remain in
[docs/release-gates.md](docs/release-gates.md), including the mutation lane's
Python 3.13 requirement.

## Conditional UI and report verification

When HTML/report presentation changes, open the generated
`output/demo/dashboard-*.html` and inspect the changed views with synthetic data.
For serve changes, run the fixture route tests in `tests/test_serve.py` with the
`serve` extra and follow [the web UI guide](docs/audit-serve.md) using
`output/demo/`. Do not start a live audit or submit provider/writeback actions to
check a UI change. Browser checks are conditional on changed presentation or
interaction; a documentation-only PR does not require them. Synthetic output
and route tests do not establish production or human acceptance.

## Coding Conventions

These conventions must be followed in all contributions:

- **Type hints on all functions** — parameters and return types, always. Use `from __future__ import annotations` at the top of each module.
- **f-strings** — use f-strings for string interpolation, not `%` formatting or `.format()`.
- **`pathlib` over `os.path`** — use `Path` objects for all file system operations. `os.path.join`, `os.listdir`, etc. are not welcome.
- **`snake_case`** for all file names, function names, and variable names.
- **No PyGithub** — the project intentionally uses raw `requests` calls to the GitHub REST API v3. Do not introduce `PyGithub`, `ghapi`, or any other GitHub client library.
- **No external analysis frameworks** — keep the dependency footprint minimal. Do not add AST analysis libraries, complexity frameworks, or linting engines as runtime dependencies. Pure Python + stdlib is the default; add a dependency only when the value is unambiguous.
- **No hardcoded usernames or tokens** — credentials come from environment variables (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, `NOTION_TOKEN`). Usernames come from CLI arguments.
- **No silent error swallowing** — always log or re-raise exceptions. The analyzer pipeline uses `logger.warning(...)` before returning a zero-score fallback result; follow the same pattern.

## Adding a New Analyzer

Analyzers live in `src/github_repo_auditor/analyzers/`. Each one scores a single dimension (0.0–1.0) and returns an `AnalyzerResult`.

### Step 1 — Create the module

Create `src/github_repo_auditor/analyzers/<your_dimension>.py` and implement a class that extends `BaseAnalyzer`:

```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from github_repo_auditor.analyzers.base import BaseAnalyzer
from github_repo_auditor.models import AnalyzerResult, RepoMetadata

if TYPE_CHECKING:
    from github_repo_auditor.github_client import GitHubClient


class YourDimensionAnalyzer(BaseAnalyzer):
    name = "your_dimension"

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

Open `src/github_repo_auditor/analyzers/__init__.py` and:

1. Import your new class at the top.
2. Append an instance to `ALL_ANALYZERS`.

```python
from github_repo_auditor.analyzers.your_dimension import YourDimensionAnalyzer

ALL_ANALYZERS = [
    ...
    YourDimensionAnalyzer(),
]
```

### Step 3 — Add a weight in the scorer

For a completeness-scored dimension, open `src/github_repo_auditor/scorer.py` and add your dimension name to the `WEIGHTS` dict. Interest is scored separately; advisory dimensions such as `description` remain unweighted. Weights must sum to `1.0` after adding the new entry, so adjust existing weights proportionally.

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
- [ ] New analyzer (if any) is registered in `ALL_ANALYZERS` and, if completeness-scored, has a weight in `WEIGHTS`.
- [ ] New tests added for any new public functions or analyzer logic.
- [ ] `CHANGELOG.md` updated under `## [Unreleased]` with a brief description of the change.
- [ ] Commit messages follow conventional commits: `feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`.

## Questions

Open an issue on GitHub. Please include the output of `audit --help` and your Python version (`python3 --version`) when reporting bugs.
