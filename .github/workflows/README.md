# GitHub Actions Workflows

## `ci.yml` — Continuous Integration

Runs on all pushes and pull requests to `main`. Superseded runs are canceled
automatically.

CI runs the canonical Python 3.11 lane. This includes documentation-only pull requests
because branch protection requires the `test (3.11)` check before merge.

Steps:
1. Install dependencies via `pip install -e ".[dev]"`
2. Run the full test suite with `pytest tests/ -v --tb=short`
3. Lint with `ruff check src/ tests/`
4. Type-check the extracted operator trend seams with scoped `mypy`

No secrets are required for CI.

## `pypi.yml` — Manual PyPI Publish

Runs manually via `workflow_dispatch` after PyPI Trusted Publishing has been
configured for this repository. It does not run on normal pushes or tags.

Steps:
1. Validate that the requested ref is a `v*` release tag.
2. Build the wheel and source distribution from that tag.
3. Run `twine check`.
4. Upload the checked distributions as a workflow artifact.
5. Publish from the protected `pypi` environment using PyPI Trusted Publishing.

No PyPI token secret is required. The publish job uses GitHub OIDC with
`id-token: write`, which must match the PyPI Trusted Publisher configuration:
owner `saagpatel`, repository `GithubRepoAuditor`, workflow `pypi.yml`, and
environment `pypi`.

## `audit.yml` — Manual Automated Audit

Runs manually via `workflow_dispatch`. No automatic weekly schedule is enabled; this
keeps public CI usage intentional and avoids opening or updating scheduled handoff
issues unless an operator starts the workflow.

Steps:
1. Install the package with config support.
2. Restore cached audit history and incremental fingerprints.
3. Run the audit in `standard` workbook mode, using incremental mode when a trustworthy cached baseline already exists.
4. Run `audit <username> --control-center` to generate the read-only operator triage artifact.
5. Inspect the canonical scheduled handoff issue state, then run `python3 -m src.scheduled_handoff --output-dir output ...` to build the scheduled handoff JSON + Markdown summary with the right lifecycle action.
6. Upload `output/` as the primary artifact output.
7. Open, update, close, or reopen one canonical `scheduled-audit-handoff` issue depending on whether the latest handoff is noisy or quiet.

The workflow does not commit generated runtime artifacts back into the repository.

### Required secrets

- `AUDIT_TOKEN`: GitHub Personal Access Token used by the audit itself when private-repo access or higher rate limits are needed.
- `GITHUB_TOKEN`: GitHub Actions token used to create or update the optional scheduled handoff issue.

### Manual trigger

Go to **Actions → Scheduled Audit → Run workflow** and optionally override the username.
