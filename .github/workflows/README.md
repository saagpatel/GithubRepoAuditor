# GitHub Actions Workflows

## `ci.yml` — Continuous Integration

Runs on every push and pull request to `main`. Tests against Python 3.11, 3.12, and 3.13.

Steps:
1. Install dependencies via `pip install -e ".[dev]"`
2. Run the full test suite with `pytest tests/ -v --tb=short`
3. Lint with `ruff check src/ tests/`

No secrets are required for CI.

## `audit.yml` — Weekly Automated Audit

Runs every Sunday at 06:00 UTC, or manually via `workflow_dispatch`.

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
